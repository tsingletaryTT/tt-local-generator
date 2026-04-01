# tt-local-generator

A GTK4 desktop UI for generating videos and images with Tenstorrent hardware:
- **Video** — [Wan2.2-T2V-A14B-Diffusers](https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B-Diffusers) on P150x4
- **Image** — [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) on 4× p300c

Both run via a local [tt-inference-server](https://github.com/tenstorrent/tt-inference-server) Docker container.

## Features

- **Server control** — ▶ Start / ■ Stop the inference server from the UI; startup log streams inline; status indicator turns teal when ready
- **Responsive gallery** — card grid re-flows automatically as the window is resized (no fixed column count)
- **Prompt queue** — write the next prompt while a generation is running; jobs execute automatically in sequence
- **Inline video player** — hover a card to preview the clip; click for the full detail panel with playback controls
- **Full-size player** — maximized window with F for true fullscreen, Space to play/pause, Esc to close
- **Trash / delete** — 🗑 button on each card removes the generation from history and deletes its files from disk
- **Generation history** — all outputs saved to `~/.local/share/tt-video-gen/` and reloaded on launch
- **Iterate** — ↺ button re-populates the prompt panel from any past generation for quick refinement
- **Job recovery** — re-attach to server jobs that survived a UI crash
- **Seed image** — attach a reference image to guide Wan2.2's motion and composition
- **Style chips** — one-click prompt modifiers (camera moves, lighting, style, quality)
- **Dual-mode** — toggle between video (Wan2.2) and image (FLUX) generation; server start/stop is context-aware
- **App icon** — Tenstorrent icon in titlebar, taskbar, and Alt+Tab switcher
- **Desktop entry** — "TT Generator" appears in GNOME Activities / KDE app launcher after setup

## Quick start

```bash
# 1. One-shot setup (Ubuntu 24.04)
git clone https://github.com/tsingletaryTT/tt-local-generator.git ~/code/tt-local-generator
cd ~/code/tt-local-generator
./setup_ubuntu.sh

# 2. Launch the UI
/usr/bin/python3 main.py

# 3. Click "▶ Start" in the control panel (or run the script directly)
./start_wan.sh          # Wan2.2 video server — wait ~5 min for "Application startup complete"
./start_flux.sh         # FLUX image server
./start_wan.sh --stop   # stop whichever server is running
```

See **[GUIDE.md](GUIDE.md)** for the full walkthrough: server setup, API tour, troubleshooting, chaining clips, prompt generation, and configuration reference.

## Requirements

- Ubuntu 22.04+ (24.04 recommended)
- Tenstorrent accelerator (P150x4 for Wan2.2 video; 4× p300c for FLUX image)
- [tt-inference-server](https://github.com/tenstorrent/tt-inference-server) configured
- System `python3` with `python3-gi` (GTK4 bindings — **not pip-installable**, must be system packages)
- `ffmpeg`, GStreamer (`libgtk-4-media-gstreamer`, `gstreamer1.0-libav`)

## Architecture

| File | Purpose |
|---|---|
| `main.py` | `Gtk.Application` entry point |
| `main_window.py` | All GTK4 widgets (`MainWindow`, `GenerationCard`, `GalleryWidget`, `ControlPanel`, `DetailPanel`) |
| `worker.py` | `GenerationWorker` / `ImageGenerationWorker` — pure Python, no GUI imports |
| `api_client.py` | HTTP client for the inference server |
| `history_store.py` | Persistent JSON history + file path management |
| `start_wan.sh` | Wan2.2 video server launch script (`--stop`, `--gui` flags) |
| `start_flux.sh` | FLUX image server launch script (`--stop`, `--gui`, `--schnell` flags) |
| `setup_ubuntu.sh` | One-shot Ubuntu 24.04 dependency installer (pulls Docker image, installs desktop entry) |
| `assets/` | Bundled assets: `tenstorrent.png` icon, `ai.tenstorrent.tt-video-gen.desktop` |

## License

Apache 2.0
