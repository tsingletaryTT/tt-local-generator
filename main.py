#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
"""
TT Local Video Generator
========================
GTK4 GUI for generating videos with Wan2.2-T2V-A14B-Diffusers via a local
tt-inference-server instance. Tracks generation history and supports iteration.

Usage:
    python3 main.py [--server http://localhost:8000]

Requires system python3-gi (GTK4 bindings) — install via:
    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0
"""
import argparse
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gio, GdkPixbuf

from main_window import MainWindow

# Path to the bundled Tenstorrent icon (32×32 PNG, fetched from tenstorrent.com)
_ICON_PATH = Path(__file__).parent / "assets" / "tenstorrent.png"


def main():
    parser = argparse.ArgumentParser(description="TT Local Video Generator")
    parser.add_argument(
        "--server",
        default="http://localhost:8000",
        help="tt-inference-server base URL (default: http://localhost:8000)",
    )
    # GTK consumes its own argv; parse known args only so GTK flags don't cause errors
    args, gtk_args = parser.parse_known_args()

    app = Gtk.Application(application_id="ai.tenstorrent.tt-video-gen")
    # Allow multiple instances — avoids silent no-op when an existing session-bus
    # registration is present (e.g. a stale process or a second launch).
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)

    def on_activate(application):
        win = MainWindow(app=application, server_url=args.server)
        # Set window icon from bundled asset; fall back gracefully if missing.
        if _ICON_PATH.exists():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(_ICON_PATH))
                win.set_icon_name("ai.tenstorrent.tt-video-gen")  # XDG name
                # GTK4 uses the application icon; set it via the display's
                # default icon list as a pixbuf fallback.
                Gtk.Window.set_default_icon_name("ai.tenstorrent.tt-video-gen")
            except Exception:
                pass
        win.present()

    app.connect("activate", on_activate)
    sys.exit(app.run([sys.argv[0]] + gtk_args))


if __name__ == "__main__":
    main()
