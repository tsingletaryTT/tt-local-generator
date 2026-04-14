#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
"""
inventory_server.py — HTTP server exposing the local tt-video-gen history
and media files so that a remote GUI instance (--server http://remote:8000)
can browse and stream/download the generated video library.

Endpoints
---------
GET /inventory/health           {"status": "ok", "records": N}
GET /inventory/records          JSON array of GenerationRecord dicts with all
                                local file paths rewritten to inventory URLs.
GET /inventory/media/<filename> Stream the named file from local storage
                                (looks in videos/, images/, thumbnails/).

Usage (run on the machine that holds the videos):
    python3 app/inventory_server.py            # default port 8002
    python3 app/inventory_server.py --port 9000

Or via tt-ctl:
    ./tt-ctl serve-inventory
    ./tt-ctl serve-inventory --port 9000

The GUI connects automatically when started with --server http://that-host:8000;
it derives the inventory URL as http://that-host:8002.

Only stdlib is required — no FastAPI / uvicorn dependency.
"""

import argparse
import json
import logging
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

# Allow running directly from the repo root or from inside app/
sys.path.insert(0, str(Path(__file__).parent))

log = logging.getLogger(__name__)

DEFAULT_PORT = 8002


# ── Media directory lookup ────────────────────────────────────────────────────

def _media_search_dirs() -> list:
    """Return the directories to scan when serving a media file by name."""
    from history_store import VIDEOS_DIR, IMAGES_DIR, THUMBNAILS_DIR  # noqa: PLC0415
    return [VIDEOS_DIR, IMAGES_DIR, THUMBNAILS_DIR]


# ── Record serialisation ──────────────────────────────────────────────────────

def _build_records_json(base_url: str) -> bytes:
    """
    Read all local GenerationRecords, rewrite every file path to an inventory
    media URL, and return the serialised JSON bytes.
    """
    from history_store import HistoryStore  # noqa: PLC0415

    store = HistoryStore()
    records = store.all_records()

    def path_to_url(p: str) -> str:
        if not p:
            return ""
        name = Path(p).name
        return f"{base_url}/inventory/media/{name}"

    out = []
    for rec in records:
        out.append({
            "id":                  rec.id,
            "prompt":              rec.prompt,
            "negative_prompt":     rec.negative_prompt,
            "num_inference_steps": rec.num_inference_steps,
            "seed":                rec.seed,
            "created_at":          rec.created_at,
            "duration_s":          rec.duration_s,
            "media_type":          rec.media_type,
            "model":               rec.model,
            "guidance_scale":      rec.guidance_scale,
            "extra_meta":          rec.extra_meta,
            # Paths rewritten to streamable inventory URLs.
            # Clients use these URLs to download media on demand.
            "video_url":           path_to_url(rec.video_path),
            "thumbnail_url":       path_to_url(rec.thumbnail_path),
            "image_url":           path_to_url(rec.image_path),
            "seed_image_url":      path_to_url(rec.seed_image_path),
        })
    return json.dumps(out, indent=2).encode("utf-8")


# ── HTTP handler ──────────────────────────────────────────────────────────────

class InventoryHandler(BaseHTTPRequestHandler):
    """Request handler for the inventory HTTP server.

    Class attribute _base_url is set by serve() before the server starts so
    that media URLs in /inventory/records point at the correct host:port.
    """

    server_version = "tt-inventory/1.0"
    _base_url: str = f"http://localhost:{DEFAULT_PORT}"

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path   = unquote(parsed.path).rstrip("/")

        if path == "/inventory/health":
            self._health()
        elif path == "/inventory/records":
            self._records()
        elif path.startswith("/inventory/media/"):
            filename = path[len("/inventory/media/"):]
            self._media(filename)
        else:
            self._not_found()

    # ── Endpoint implementations ──────────────────────────────────────────────

    def _health(self):
        from history_store import HistoryStore  # noqa: PLC0415
        n = len(HistoryStore().all_records())
        body = json.dumps({"status": "ok", "records": n}).encode()
        self._respond(200, "application/json", body)

    def _records(self):
        try:
            body = _build_records_json(self.__class__._base_url)
            self._respond(200, "application/json", body)
        except Exception as exc:
            log.exception("inventory: failed to serialise records")
            body = json.dumps({"error": str(exc)}).encode()
            self._respond(500, "application/json", body)

    def _media(self, filename: str):
        # Strip path-traversal components — only the final filename is used.
        filename = Path(filename).name
        if not filename:
            self._not_found()
            return

        for directory in _media_search_dirs():
            candidate = directory / filename
            if candidate.exists() and candidate.is_file():
                self._stream_file(candidate)
                return

        self._not_found()

    # ── Low-level helpers ─────────────────────────────────────────────────────

    def _stream_file(self, path: Path):
        """Send a file to the client in 64 KiB chunks (handles large videos)."""
        size = path.stat().st_size
        ct, _  = mimetypes.guess_type(str(path))
        ct = ct or "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            with open(path, "rb") as fh:
                while True:
                    chunk = fh.read(65_536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected mid-transfer — harmless

    def _respond(self, code: int, ct: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _not_found(self):
        self._respond(404, "text/plain", b"Not found\n")

    def log_message(self, fmt, *args):  # suppress per-request stderr noise
        log.debug("inventory: " + (fmt % args))


# ── Public entry point ────────────────────────────────────────────────────────

def serve(port: int = DEFAULT_PORT, host: str = "0.0.0.0") -> None:
    """Start the inventory HTTP server (blocks until KeyboardInterrupt).

    Args:
        port: TCP port to listen on (default 8002).
        host: Interface to bind (default 0.0.0.0 = all interfaces).
    """
    # Compute the base URL for media links in /inventory/records.
    # When listening on 0.0.0.0 we don't know the external hostname, so we
    # use 'localhost' as a fallback — the GUI overrides with the configured host.
    display_host = "localhost" if host == "0.0.0.0" else host
    InventoryHandler._base_url = f"http://{display_host}:{port}"

    server = ThreadingHTTPServer((host, port), InventoryHandler)
    print(f"[inventory] Serving on http://0.0.0.0:{port}")
    print(f"[inventory] Records:  http://{display_host}:{port}/inventory/records")
    print(f"[inventory] Health:   http://{display_host}:{port}/inventory/health")
    print("[inventory] Press Ctrl+C to stop.\n")
    log.info("inventory server listening on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[inventory] Stopped.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(
        description="tt-video-gen inventory server — share your local video library"
    )
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"TCP port to listen on (default {DEFAULT_PORT})")
    p.add_argument("--host", default="0.0.0.0",
                   help="Interface to bind (default 0.0.0.0)")
    args = p.parse_args()
    serve(args.port, args.host)
