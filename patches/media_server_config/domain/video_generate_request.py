# SPDX-License-Identifier: Apache-2.0
#
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
#
# Hotpatch delivered via patches/media_server_config/domain/
# Extends VideoGenerateRequest with num_frames so SkyReels jobs can request
# variable video length via the REST API.
#
# Bound-mounted into the container at:
#   ~/tt-metal/server/domain/video_generate_request.py
#
# CHANGE from upstream: added num_frames field (Optional[int], default None).
# All other fields are unchanged.

from typing import Optional

from domain.base_request import BaseRequest
from pydantic import Field


class VideoGenerateRequest(BaseRequest):
    # Required fields
    prompt: str

    # Optional fields
    negative_prompt: Optional[str] = None
    num_inference_steps: Optional[int] = Field(default=20, ge=12, le=50)
    seed: Optional[int] = None
    # Number of output video frames; None means the runner uses its default.
    # Valid frame counts for SkyReels/WAN: (N-1) % 4 == 0  →  9, 13, 17, 21, 25, 29, 33, …
    num_frames: Optional[int] = None
