# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
#
# Hotpatch: WanPipelineAnimate — TT-hardware animate pipeline for Wan2.2-Animate-14B.
#
# Architecture notes
# ------------------
# Animate-14B is a fine-tune of I2V-A14B.  The transformer and VAE architectures
# are identical; only the checkpoint weights differ.  The fine-tuning teaches the
# model to transfer motion from a reference video onto a supplied character image.
#
# TT hardware strategy
# --------------------
# We treat the character image as the I2V conditioning reference frame (frame_pos=0)
# and delegate all TT-specific encoding / inference to WanPipelineI2V unchanged.
# The reference video is accepted by the runner but is not passed to the pipeline in
# v1 — motion comes from the fine-tuned weights rather than explicit conditioning.
#
# Mount path (via run_docker_server.py tt_dit hotpatch mechanism, --dev-mode):
#   patches/tt_dit/pipelines/wan/pipeline_wan_animate.py →
#   ~/tt-metal/models/tt_dit/pipelines/wan/pipeline_wan_animate.py
#
# Python import path inside the container:
#   models.tt_dit.pipelines.wan.pipeline_wan_animate

import os

from .pipeline_wan import WanPipeline
from .pipeline_wan_i2v import ImagePrompt, WanPipelineI2V


class WanPipelineAnimate(WanPipelineI2V):
    """
    TT-hardware Animate-14B pipeline.

    Thin subclass of WanPipelineI2V that swaps in the Animate checkpoint.
    The caller passes a character_image (PIL.Image); this class wraps it in an
    ImagePrompt and delegates everything else to WanPipelineI2V.

    Args (via __call__):
        character_image (PIL.Image): the character to animate.
        reference_video_frames (list[PIL.Image] | None): motion source frames,
            accepted for API compatibility but not used in v1.
        **kwargs: forwarded to WanPipelineI2V.__call__
            (prompt, num_frames, height, width, num_inference_steps, seed, …).
    """

    # Default checkpoint — overridden by MODEL_WEIGHTS_DIR env var at runtime.
    CHECKPOINT = "Wan-AI/Wan2.2-Animate-14B-Diffusers"

    def __init__(self, *args, **kwargs):
        # Use Animate checkpoint unless the caller or env already specifies one.
        if "checkpoint_name" not in kwargs:
            kwargs["checkpoint_name"] = os.environ.get(
                "MODEL_WEIGHTS_DIR", self.CHECKPOINT
            )
        # WanPipelineI2V.__init__ will load the scheduler from checkpoint_name
        # (if not already provided) and call WanPipeline.__init__.
        super().__init__(*args, **kwargs)

    @staticmethod
    def create_pipeline(*args, **kwargs):
        """
        Factory method — mirrors WanPipelineI2V.create_pipeline but points at
        the Animate checkpoint and uses WanPipelineAnimate as the pipeline class.
        """
        if "checkpoint_name" not in kwargs:
            kwargs["checkpoint_name"] = os.environ.get(
                "MODEL_WEIGHTS_DIR", WanPipelineAnimate.CHECKPOINT
            )
        return WanPipeline.create_pipeline(
            *args, pipeline_class=WanPipelineAnimate, **kwargs
        )

    def __call__(self, character_image, reference_video_frames=None, **kwargs):
        """
        Run Animate inference on TT hardware.

        Wraps character_image in an ImagePrompt at frame_pos=0 and delegates to
        WanPipelineI2V.__call__, which handles TT encoding and denoising.

        Args:
            character_image: PIL.Image — character to animate.
            reference_video_frames: list[PIL.Image] | None — motion source frames.
                Accepted for API compatibility; not used in v1 (motion is encoded
                implicitly in the fine-tuned Animate weights).
            **kwargs: forwarded to WanPipelineI2V.__call__.
        """
        image_prompt = ImagePrompt(image=character_image, frame_pos=0)
        return super().__call__(image_prompt=image_prompt, **kwargs)
