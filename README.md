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
| `prompt_client.py` | HTTP client for the prompt gen server — no GTK deps |
| `prompt_server.py` | Local Qwen3-0.6B chat server (CPU, port 8001) |
| `start_prompt_gen.sh` | Prompt gen server launch script (`--stop`, `--gui` flags) |
| `prompts/prompt_generator.md` | System prompt defining the cinematic mad-libs format |

## Prompt generator (optional)

The **✨ Inspire me** button below the prompt textarea generates cinematic prompts
using a local [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) model running
entirely on CPU — it does not use the TT chips and coexists with a running video/image
server on port 8000.

### One-time setup

```bash
pip install transformers torch accelerate
# The model (~1.2 GB) downloads from Hugging Face automatically on first start
```

### Starting the server

```bash
./start_prompt_gen.sh          # start, tail log (Ctrl-C leaves server running)
./start_prompt_gen.sh --stop   # stop
```

Or just click **✨ Inspire me** in the app — if the server isn't running, the UI
will offer to start it for you.

### Usage

- With an **empty prompt box**: generates a fresh cinematic prompt for the current
  mode (Video / Image / Animate) using the model's built-in word banks.
- With **existing text**: uses your text as a creative seed and generates a new
  prompt inspired by it. The existing text is replaced by the result.

### Quick health check

```bash
curl -s http://localhost:8001/health
# → {"status":"ok","model_ready":true}
```

## License

Apache 2.0
