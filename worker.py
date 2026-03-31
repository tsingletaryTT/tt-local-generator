#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
"""
Background workers for media generation.

Two worker classes, both with identical run_with_callbacks() interfaces:

  GenerationWorker — Wan2.2 video (async/job-based):
    1. Submit job to server (or re-attach via _job_id_override)
    2. Poll status every 3 seconds until complete or failed
    3. Download the MP4 to local storage
    4. Extract a thumbnail (first frame) via ffmpeg
    5. Write prompt sidecar .txt
    6. Persist to history

  ImageGenerationWorker — FLUX.1-dev image (synchronous):
    1. POST /v1/images/generations — blocks until the server responds (~15–90 s)
    2. Decode base64 response and write JPEG to local storage
    3. Create a scaled thumbnail via ffmpeg (falls back to copy)
    4. Write prompt sidecar .txt
    5. Persist to history

Communication back to the UI is via plain callbacks. The caller (GTK main window)
wraps each callback in GLib.idle_add() so UI updates always happen on the main
thread. Never import or touch GTK widgets from here.
"""
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from api_client import APIClient
from history_store import THUMBNAILS_DIR, GenerationRecord, HistoryStore


class GenerationWorker:
    """
    Runs a single video generation job end-to-end in a background thread.

    Usage (GTK):
        gen = GenerationWorker(client, store, prompt, ...)
        thread = threading.Thread(target=lambda: gen.run_with_callbacks(
            on_progress=lambda msg: GLib.idle_add(update_status, msg),
            on_finished=lambda rec: GLib.idle_add(handle_done, rec),
            on_error=lambda msg: GLib.idle_add(handle_error, msg),
        ), daemon=True)
        thread.start()
    """

    POLL_INTERVAL = 3.0

    def __init__(
        self,
        client: APIClient,
        store: HistoryStore,
        prompt: str,
        negative_prompt: str,
        num_inference_steps: int,
        seed: int,
        seed_image_path: str = "",
    ):
        self._client = client
        self._store = store
        self._prompt = prompt
        self._negative_prompt = negative_prompt
        self._steps = num_inference_steps
        self._seed = seed
        self._seed_image_path = seed_image_path
        self._cancelled = False
        self._job_id_override: Optional[str] = None  # set to skip submit (recovery)
        self._lock = threading.Lock()

    def cancel(self) -> None:
        """Request early termination. Thread-safe."""
        with self._lock:
            self._cancelled = True

    def _is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def _running(self) -> bool:
        """False once cancel() has been called — used by MainWindow to detect activity."""
        return not self._is_cancelled()

    def run_with_callbacks(
        self,
        on_progress: Callable[[str], None],
        on_finished: Callable[[GenerationRecord], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Execute the full pipeline. Call this from a background thread.

        The callbacks will be invoked FROM THIS THREAD — callers must wrap them
        in GLib.idle_add() (or equivalent) to safely update GTK widgets.
        """
        start_time = time.monotonic()

        # ── 1. Submit or re-attach ────────────────────────────────────────────
        if self._job_id_override:
            job_id = self._job_id_override
            on_progress(f"Re-attached to job {job_id[:8]}…")
        else:
            try:
                on_progress("Submitting job…")
                seed_arg = self._seed if self._seed >= 0 else None
                job_id = self._client.submit(
                    prompt=self._prompt,
                    negative_prompt=self._negative_prompt or None,
                    num_inference_steps=self._steps,
                    seed=seed_arg,
                )
            except Exception as e:
                on_error(f"Submit failed: {e}")
                return
            on_progress(f"Job queued ({job_id[:8]}…)")

        # ── 2. Poll until complete ────────────────────────────────────────────
        while not self._is_cancelled():
            try:
                status, err = self._client.poll_status(job_id)
            except Exception as e:
                on_error(f"Poll error: {e}")
                return

            if status == "completed":
                break
            if status in ("failed", "cancelled"):
                on_error(f"Job {status}: {err or 'no details'}")
                return

            elapsed = int(time.monotonic() - start_time)
            on_progress(f"Generating… {elapsed}s ({status})")
            time.sleep(self.POLL_INTERVAL)

        if self._is_cancelled():
            on_error("Cancelled by user")
            return

        # ── 3. Build record ───────────────────────────────────────────────────
        duration = time.monotonic() - start_time

        persisted_seed_image = ""
        if self._seed_image_path and Path(self._seed_image_path).is_file():
            src = Path(self._seed_image_path)
            dest = THUMBNAILS_DIR / f"seed_{job_id[:8]}{src.suffix}"
            try:
                shutil.copy2(src, dest)
                persisted_seed_image = str(dest)
            except Exception:
                persisted_seed_image = self._seed_image_path

        record = GenerationRecord.new(
            job_id=job_id,
            prompt=self._prompt,
            negative_prompt=self._negative_prompt,
            num_inference_steps=self._steps,
            seed=self._seed,
            duration_s=round(duration, 1),
            seed_image_path=persisted_seed_image,
        )

        # ── 4. Download ───────────────────────────────────────────────────────
        try:
            on_progress(f"Downloading video… ({duration:.0f}s total)")
            self._client.download(job_id, Path(record.video_path))
        except Exception as e:
            on_error(f"Download failed: {e}")
            return

        # ── 5. Thumbnail ──────────────────────────────────────────────────────
        self._extract_thumbnail(record.video_path, record.thumbnail_path)

        # ── 6. Sidecar ────────────────────────────────────────────────────────
        self._write_prompt_sidecar(record)

        # ── 7. Persist and notify ─────────────────────────────────────────────
        self._store.append(record)
        on_finished(record)

    def _write_prompt_sidecar(self, record: GenerationRecord) -> None:
        """Write a .txt metadata file next to the MP4. Silently skips on I/O error."""
        txt_path = Path(record.video_path).with_suffix(".txt")
        lines = [f"prompt: {record.prompt}"]
        if record.negative_prompt:
            lines.append(f"negative_prompt: {record.negative_prompt}")
        lines += [
            f"steps: {record.num_inference_steps}",
            f"seed: {record.seed}",
            f"generated: {record.created_at}",
            f"duration_s: {record.duration_s}",
        ]
        if record.seed_image_path:
            lines.append(f"seed_image: {record.seed_image_path}")
        try:
            txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _extract_thumbnail(self, video_path: str, thumbnail_path: str) -> None:
        """
        Extract the first frame as a JPEG thumbnail via ffmpeg.
        Silently skips if ffmpeg is unavailable or fails.
        stdin=DEVNULL prevents ffmpeg from blocking on terminal input.
        """
        Path(thumbnail_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-update", "1",   # write single image, not a sequence
                    thumbnail_path,
                ],
                stdin=subprocess.DEVNULL,   # don't block waiting for [q] keypress
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


# ── FLUX image generation worker ───────────────────────────────────────────────

class ImageGenerationWorker:
    """
    Runs a single FLUX image generation request end-to-end in a background thread.

    The image API is synchronous: the POST request blocks until the image is ready.
    No polling is required. The response contains the image as a base64-encoded JPEG.

    Usage (GTK):
        gen = ImageGenerationWorker(client, store, prompt, ...)
        thread = threading.Thread(target=lambda: gen.run_with_callbacks(
            on_progress=lambda msg: GLib.idle_add(update_status, msg),
            on_finished=lambda rec: GLib.idle_add(handle_done, rec),
            on_error=lambda msg: GLib.idle_add(handle_error, msg),
        ), daemon=True)
        thread.start()
    """

    def __init__(
        self,
        client: APIClient,
        store: HistoryStore,
        prompt: str,
        negative_prompt: str,
        num_inference_steps: int,
        seed: int,
        guidance_scale: float = 3.5,
    ):
        self._client = client
        self._store = store
        self._prompt = prompt
        self._negative_prompt = negative_prompt
        self._steps = num_inference_steps
        self._seed = seed
        self._guidance_scale = guidance_scale
        self._cancelled = False
        self._lock = threading.Lock()

    def cancel(self) -> None:
        """Request early termination. Thread-safe."""
        with self._lock:
            self._cancelled = True

    def _is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def _running(self) -> bool:
        """False once cancel() has been called."""
        return not self._is_cancelled()

    def run_with_callbacks(
        self,
        on_progress: Callable[[str], None],
        on_finished: Callable[[GenerationRecord], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Execute the full pipeline. Call this from a background thread.

        The callbacks will be invoked FROM THIS THREAD — callers must wrap them
        in GLib.idle_add() (or equivalent) to safely update GTK widgets.
        """
        start_time = time.monotonic()
        job_id = str(uuid.uuid4())   # local ID; image API has no server-side job ID

        # ── 1. Generate ───────────────────────────────────────────────────────
        try:
            on_progress("Generating image with FLUX.1-dev…")
            seed_arg = self._seed if self._seed >= 0 else None
            image_bytes = self._client.generate_image(
                prompt=self._prompt,
                negative_prompt=self._negative_prompt or None,
                num_inference_steps=self._steps,
                seed=seed_arg,
                guidance_scale=self._guidance_scale,
            )
        except Exception as e:
            on_error(f"Image generation failed: {e}")
            return

        if self._is_cancelled():
            on_error("Cancelled by user")
            return

        duration = time.monotonic() - start_time

        # ── 2. Build record ───────────────────────────────────────────────────
        record = GenerationRecord.new_image(
            job_id=job_id,
            prompt=self._prompt,
            negative_prompt=self._negative_prompt,
            num_inference_steps=self._steps,
            seed=self._seed,
            duration_s=round(duration, 1),
            guidance_scale=self._guidance_scale,
        )

        # ── 3. Save image ─────────────────────────────────────────────────────
        try:
            on_progress(f"Saving image… ({duration:.0f}s)")
            Path(record.image_path).parent.mkdir(parents=True, exist_ok=True)
            Path(record.image_path).write_bytes(image_bytes)
        except Exception as e:
            on_error(f"Failed to save image: {e}")
            return

        # ── 4. Thumbnail ──────────────────────────────────────────────────────
        self._make_thumbnail(record.image_path, record.thumbnail_path)

        # ── 5. Sidecar ────────────────────────────────────────────────────────
        self._write_prompt_sidecar(record)

        # ── 6. Persist and notify ─────────────────────────────────────────────
        self._store.append(record)
        on_finished(record)

    def _make_thumbnail(self, image_path: str, thumbnail_path: str) -> None:
        """
        Create a _THUMB_W × _THUMB_H thumbnail of the generated image via ffmpeg.
        Falls back to a straight copy if ffmpeg is unavailable or fails.
        """
        Path(thumbnail_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", image_path,
                    "-vf", "scale=200:112:force_original_aspect_ratio=decrease,"
                           "pad=200:112:(ow-iw)/2:(oh-ih)/2",
                    "-q:v", "3",
                    thumbnail_path,
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # No ffmpeg — just copy the original as the "thumbnail"
            try:
                shutil.copy2(image_path, thumbnail_path)
            except Exception:
                pass

    def _write_prompt_sidecar(self, record: GenerationRecord) -> None:
        """Write a .txt metadata file next to the JPEG. Silently skips on I/O error."""
        txt_path = Path(record.image_path).with_suffix(".txt")
        lines = [f"prompt: {record.prompt}"]
        if record.negative_prompt:
            lines.append(f"negative_prompt: {record.negative_prompt}")
        lines += [
            f"steps: {record.num_inference_steps}",
            f"guidance_scale: {record.guidance_scale}",
            f"seed: {record.seed}",
            f"generated: {record.created_at}",
            f"duration_s: {record.duration_s}",
        ]
        try:
            txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass
