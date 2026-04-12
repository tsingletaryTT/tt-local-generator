# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
#
# TTSkyReelsRunner — server runner for SkyReels-V2-DF-1.3B-540P on Tenstorrent Blackhole.
#
# This file is a hotpatch delivered via patches/media_server_config/tt_model_runners/.
# It is bind-mounted into the container at:
#   ~/tt-metal/server/tt_model_runners/skyreels_runner.py
#
# Design notes
# ============
# SkyReels-V2-DF-1.3B-540P is a WAN2.2-derived text-to-video model.  Its transformer
# architecture is weight-compatible with WanTransformerBlock in tt-metal, making TTNN
# acceleration straightforward via models.tt_dit.
#
# This runner is intentionally a standalone file (not inside dit_runners.py) to avoid
# triggering the dit_runner_log_map dict lookup in that module at import time; with a
# non-WAN model_runner string the lookup raises KeyError before any runner is created.
#
# Mount path (via apply_patches.sh + run_docker_server.py media_server_config mechanism):
#   patches/media_server_config/tt_model_runners/skyreels_runner.py
#   → ~/tt-metal/server/tt_model_runners/skyreels_runner.py
#
# This file is registered in runner_fabric.py (also hotpatched) under
# ModelRunners.TT_SKYREELS_V2.

import asyncio
import os

import ttnn
from config.constants import ModelRunners, ModelServices, SupportedModels
from config.settings import get_settings
from domain.video_generate_request import VideoGenerateRequest
from tt_model_runners.base_metal_device_runner import BaseMetalDeviceRunner
from utils.logger import log_exception_chain


class TTSkyReelsRunner(BaseMetalDeviceRunner):
    """
    Runner for SkyReels-V2-DF-1.3B-540P on TT Blackhole hardware.

    Uses SkyReelsPipeline (hotpatch at
    models/tt_dit/pipelines/skyreels_v2/pipeline_skyreels.py) which wraps
    a TTNN-accelerated WanTransformer3DModel with a diffusers SkyReelsV2Pipeline
    front-end.

    Input contract (VideoGenerateRequest fields used):
      prompt              — text description of the video to generate
      negative_prompt     — negative text guidance (optional)
      num_inference_steps — denoising steps (default 20; 8 recommended for speed)
      seed                — random seed for reproducibility

    Output: numpy array of video frames (B=1, T, H, W, C) in [0, 1], encoded to
    MP4 by the video service layer.
    """

    # SkyReels-V2-DF-1.3B-540P default output resolution at the 540P checkpoint.
    # The 540P checkpoint targets 480×272 (widescreen) for short clips.
    # Valid frame counts: (N-1) % 4 == 0 → 9, 13, 17, 21, 25, 29, 33, ...
    DEFAULT_WIDTH = 480
    DEFAULT_HEIGHT = 272
    DEFAULT_NUM_FRAMES = 33       # 33 frames ≈ 1.4s @ 24fps — reasonable clip length
    DEFAULT_GUIDANCE_SCALE = 6.0  # SkyReels recommended: 5-7

    def __init__(self, device_id: str):
        super().__init__(device_id)

    def _configure_fabric(self, updated_device_params):
        """
        Pop fabric_config/fabric_tensix_config from device_params and apply via
        ttnn.set_fabric_config().  Must be called before open_mesh_device().

        Mirrors TTDiTRunner._configure_fabric() exactly — we can't inherit from
        TTDiTRunner because that module's decorators evaluate
        dit_runner_log_map[get_settings().model_runner] at import time, which
        raises KeyError for 'tt-skyreels-v2'.
        """
        try:
            fabric_config = updated_device_params.pop(
                "fabric_config", ttnn.FabricConfig.FABRIC_1D
            )
            fabric_tensix_config = updated_device_params.pop(
                "fabric_tensix_config", ttnn.FabricTensixConfig.DISABLED
            )
            reliability_mode = updated_device_params.pop(
                "reliability_mode", ttnn.FabricReliabilityMode.STRICT_INIT
            )
            ttnn.set_fabric_config(fabric_config, reliability_mode, None, fabric_tensix_config)
            return fabric_config
        except Exception as e:
            log_exception_chain(
                self.logger,
                self.device_id,
                "SkyReels fabric configuration failed",
                e,
            )
            raise RuntimeError(f"Fabric configuration failed: {str(e)}") from e

    def create_pipeline(self):
        """
        Create the SkyReels TTNN pipeline using the already-opened mesh device.

        The mesh device is opened by BaseMetalDeviceRunner.set_device() before
        create_pipeline() is called.  This method only builds the model and
        loads weights — fabric initialization was already done by _configure_fabric.

        Note: weight loading (3.5B params across 4 Blackhole chips via PCIe)
        takes 15-30 minutes.  The 3600s warmup timeout in ModelConfigs covers this.
        """
        # Lazy import: SkyReelsPipeline lives in a hotpatch file mounted at runtime.
        # Importing at module level would fail before the file is mounted.
        try:
            from models.tt_dit.pipelines.skyreels_v2.pipeline_skyreels import (
                SkyReelsPipeline,
            )
        except ImportError as exc:
            raise RuntimeError(
                "SkyReelsPipeline not found in the container.  Ensure that "
                "patches/tt_dit/pipelines/skyreels_v2/pipeline_skyreels.py exists "
                "and the server was started with --dev-mode so the tt_dit "
                "hotpatch mechanism bind-mounts it."
            ) from exc

        checkpoint_name = os.environ.get(
            "MODEL_WEIGHTS_DIR",
            SupportedModels.SKYREELS_V2_DF_1_3B_540P.value,
        )
        self.logger.info(
            f"Device {self.device_id}: Loading SkyReels pipeline from {checkpoint_name}"
        )
        try:
            return SkyReelsPipeline.create_pipeline(
                mesh_device=self.ttnn_device,
                checkpoint_name=checkpoint_name,
            )
        except Exception as e:
            log_exception_chain(
                self.logger,
                self.device_id,
                "SkyReels pipeline creation failed",
                e,
            )
            raise

    async def warmup(self) -> bool:
        """
        Load model weights and run a 2-step warmup pass.

        Mirrors TTDiTRunner.warmup() but uses a 60-minute timeout to account for
        SkyReels weight loading time on Blackhole (3.5B params, first cold start).
        """
        self.logger.info(f"Device {self.device_id}: Loading SkyReels model...")

        def distribute_block():
            self.pipeline = self.create_pipeline()

        # 60 minutes: SkyReels weight loading on first cold start can take ~30-45 min.
        weights_distribution_timeout = 3600
        try:
            await asyncio.wait_for(
                asyncio.to_thread(distribute_block),
                timeout=weights_distribution_timeout,
            )
        except asyncio.TimeoutError:
            self.logger.error(
                f"Device {self.device_id}: SkyReels model loading timed out after "
                f"{weights_distribution_timeout} seconds"
            )
            raise
        except Exception as e:
            log_exception_chain(
                self.logger,
                self.device_id,
                "Exception during SkyReels model loading",
                e,
            )
            raise

        self.logger.info(f"Device {self.device_id}: SkyReels model loaded successfully")

        # 2-step warmup pass (compiles TTNN kernels for this sequence length).
        self.run(
            [
                VideoGenerateRequest.model_construct(
                    prompt="Sunrise on a beach",
                    negative_prompt="",
                    num_inference_steps=2,
                )
            ]
        )

        self.logger.info(f"Device {self.device_id}: SkyReels warmup completed")
        return True

    def load_weights(self):
        # Weights are loaded inside create_pipeline (TTNN model's load_torch_state_dict).
        return False

    def run(self, requests: list[VideoGenerateRequest]):
        """
        Run one denoising pass and return video frames.

        Returns numpy array (1, T, H, W, C) with pixel values in [0, 1], matching
        the format returned by WanPipeline so the video service layer can encode it.
        """
        self.logger.debug(f"Device {self.device_id}: Running SkyReels inference")
        request = requests[0]

        # num_frames: use request value if provided and valid, else runner default.
        # Valid counts: (N-1) % 4 == 0  →  9, 13, 17, 21, 25, 29, 33, 65, 97, ...
        num_frames = getattr(request, "num_frames", None) or self.DEFAULT_NUM_FRAMES
        frames = self.pipeline(
            prompt=request.prompt or "",
            negative_prompt=request.negative_prompt or "",
            height=self.DEFAULT_HEIGHT,
            width=self.DEFAULT_WIDTH,
            num_frames=int(num_frames),
            num_inference_steps=request.num_inference_steps,
            guidance_scale=self.DEFAULT_GUIDANCE_SCALE,
            seed=int(request.seed or 0),
        )
        self.logger.debug(f"Device {self.device_id}: SkyReels inference completed")
        return frames

    def get_pipeline_device_params(self):
        """
        Device parameters for Blackhole hardware.

        On Blackhole, FABRIC_1D_MUX requires FabricTensixConfig.MUX and
        DispatchCoreAxis.ROW.  BaseMetalDeviceRunner.get_updated_device_params()
        converts dispatch_core_axis into a DispatchCoreConfig object before
        passing to open_mesh_device.

        This matches TTWan22Runner.get_pipeline_device_params() exactly.
        """
        device_params = {
            "fabric_config": ttnn.FabricConfig.FABRIC_1D,
        }
        if ttnn.device.is_blackhole():
            device_params["fabric_tensix_config"] = ttnn.FabricTensixConfig.MUX
            device_params["dispatch_core_axis"] = ttnn.device.DispatchCoreAxis.ROW
        return device_params
