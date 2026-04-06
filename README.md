# tt-local-generator

A GTK4 desktop UI for generating videos and images with Tenstorrent hardware.

**Supported models:**

| Mode | Model | Hardware |
|------|-------|----------|
| Video | [Wan2.2-T2V-A14B-Diffusers](https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B-Diffusers) | QB2 (P300x2) |
| Video | [Mochi-1-preview](https://huggingface.co/genmo/mochi-1-preview) | QB2 (P300x2) |
| Image | [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) | 4× p300c |
| Animate | [Wan2.2-I2V-A14B-Diffusers](https://huggingface.co/Wan-AI/Wan2.2-I2V-14B-720P-Diffusers) | CPU/CUDA (Phase 1) |

All inference runs via a local [tt-inference-server](https://github.com/tenstorrent/tt-inference-server) Docker container on port 8000.

---

## Directory layout

```
tt-local-generator/
  app/                   ← all Python source files
    main.py              ← Gtk.Application entry point
    main_window.py       ← all GTK4 widgets
    worker.py            ← background generation (no GTK imports)
    api_client.py        ← HTTP client for inference server
    server_manager.py    ← start/stop/health for all managed services
    history_store.py     ← persistent JSON history
    generate_prompt.py   ← three-tier prompt generator CLI
    prompt_client.py     ← thin wrapper: polish vs. full generation
    prompt_server.py     ← FastAPI server (Qwen3-0.6B, port 8001)
    word_banks.py        ← prompt word banks + sampling helpers
    attractor.py         ← AttractorWindow — kiosk loop
    chip_config.py       ← chip definitions from config/
    app_settings.py      ← persistent settings
    assets/              ← tenstorrent.png icon, .desktop entry
    prompts/             ← Markov seed corpus, system prompt
    config/              ← prompt_chips.yaml
  bin/                   ← shell scripts
    start_wan_qb2.sh     ← Wan2.2 on P300x2 (default)
    start_wan.sh         ← Wan2.2 on P150x4
    start_mochi.sh       ← Mochi-1 on QB2
    start_flux.sh        ← FLUX.1-dev image server
    start_animate.sh     ← Wan2.2-Animate (CPU/CUDA Phase 1)
    start_prompt_gen.sh  ← Qwen3-0.6B prompt server (CPU, port 8001)
    apply_patches.sh     ← apply patches/ to vendor/ or ~/code/tt-inference-server
    best_experience_services.sh  ← start Wan2.2 + prompt server together
  patches/               ← hotpatch files applied by apply_patches.sh
    media_server_config/ ← constants.py overrides (P300x2 timeouts, etc.)
    tt_dit/              ← pipeline fixes (dev_mode only)
  vendor/                ← shallow clone of tt-inference-server (gitignored)
    tt-inference-server/ ← pinned to VENDOR_SHA, patched by apply_patches.sh
    VENDOR_SHA           ← SHA of the vendored commit
  docker/                ← Docker image archive (Git LFS)
    tt-media-inference-server-0.11.1-bac8b34.tar.gz
    README.md
  tests/                 ← pytest test suite (83 tests)
  tt-gen                 ← launcher: starts the GUI
  tt-ctl                 ← CLI: status, history, start/stop services
  requirements.txt
```

---

## Quick start

```bash
# 1. Clone and set up
git clone https://github.com/tsingletaryTT/tt-local-generator.git ~/code/tt-local-generator
cd ~/code/tt-local-generator
./setup_ubuntu.sh

# 2. Apply patches to the vendored tt-inference-server
./bin/apply_patches.sh

# 3. Start the inference server (QB2 / P300x2)
./bin/start_wan_qb2.sh         # Wan2.2 — wait ~5 min for "Application startup complete"

# 4. Launch the UI
./tt-gen

# Or start everything at once
./bin/best_experience_services.sh
```

### Alternate start (P150x4)

```bash
./bin/start_wan.sh             # Wan2.2 on P150x4
```

### Stop any server

```bash
./bin/start_wan_qb2.sh --stop
./bin/start_wan.sh --stop
```

---

## CLI tool (`tt-ctl`)

```bash
./tt-ctl status           # server health + chip temps
./tt-ctl servers          # live status of every managed service
./tt-ctl history          # 10 most recent generations (newest first)
./tt-ctl run "a red fox"  # generate directly from the terminal

# Service management
./tt-ctl start wan2.2         # start the Wan2.2 server
./tt-ctl start prompt-server  # start the Qwen prompt server
./tt-ctl start all            # start the recommended set
./tt-ctl stop  wan2.2
./tt-ctl restart wan2.2

# Known service keys: wan2.2  mochi  flux  animate  prompt-server  all
```

---

## Features

### Generation
- **Video** — text-to-video with Wan2.2 or Mochi-1
- **Image** — text-to-image with FLUX.1-dev
- **Animate** — drive a character image with a motion video (Wan2.2-Animate-14B)
- **Seed image** — attach a reference image to guide Wan2.2's motion and composition
- **Style chips** — one-click prompt modifiers (camera moves, lighting, style, quality)
- **Prompt queue** — write the next prompt while a generation is running
- **Queue persistence** — queue survives crashes and restarts
- **Disk space guard** — generation is blocked when the output drive has < 18 GB free

### Prompt generator
- **✨ Inspire me** — always works: three-tier system (algorithmic → Markov → LLM polish)
- **Algo-only** mode when the Qwen server is offline — still generates varied prompts
- **LLM polish** when `start_prompt_gen.sh` is running (Qwen3-0.6B on CPU, port 8001)
- **Seed-text inspire** — type a rough idea, click Inspire; LLM polishes if available

### Gallery & playback
- **Responsive gallery** — card grid re-flows automatically as the window resizes
- **Inline video player** — hover to preview; click for full detail panel
- **Full-size player** — F for fullscreen, Space to play/pause, Esc to close
- **Trash / delete** — 🗑 removes a generation from history and deletes files
- **Iterate** — ↺ re-populates the prompt panel from any past generation

### Attractor Mode
- **✦ Attractor** toolbar button opens a borderless kiosk window
- Loops through gallery media with crossfades
- Continuously generates and queues new generations in the background

### Server management
- **Servers ▾** toolbar dropdown — start/stop/restart individual services from the GUI
- **Context-aware start** — Video tab starts Wan2.2 (QB2); Animate tab starts Wan2.2-Animate; Image tab starts FLUX
- **Server log panel** — pulsing progress bar and phase label during startup; expand "▸ Log" for raw output
- **Job recovery** — re-attach to server jobs that survived a UI crash

---

## Requirements

- Ubuntu 22.04+ (24.04 recommended)
- Tenstorrent QB2 (P300x2) for Wan2.2 and Mochi-1; 4× p300c for FLUX
- Docker
- System `python3` with `python3-gi` (GTK4 bindings — not pip-installable)
- `ffmpeg`, GStreamer (`libgtk-4-media-gstreamer`, `gstreamer1.0-libav`)

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 ffmpeg \
    libgtk-4-media-gstreamer gstreamer1.0-libav
```

Optional for LLM prompt polish:
```bash
pip install -r requirements.txt   # requests, markovify, pytest
# Qwen model (~1.2 GB) downloads automatically on first ./bin/start_prompt_gen.sh
```

---

## Prompt generator (CLI)

```bash
cd app/
python3 generate_prompt.py                          # algo + LLM polish, video
python3 generate_prompt.py --type image --mode markov
python3 generate_prompt.py --count 5 --no-enhance  # algo only, five prompts
python3 generate_prompt.py --raw                    # plain text (no JSON wrapper)
```

JSON output: `{"prompt": "...", "type": "video|image|animate", "source": "llm|markov|algo", "slug": "..."}`

```bash
./bin/start_prompt_gen.sh          # start Qwen server (port 8001)
./bin/start_prompt_gen.sh --stop   # stop
curl -s http://localhost:8001/health  # → {"status":"ok","model_ready":true}
```

---

## Vendored `tt-inference-server`

The repo includes a shallow clone of `tt-inference-server` at a known-good commit:

```bash
cat vendor/VENDOR_SHA          # pinned SHA
./bin/apply_patches.sh         # apply patches/ to vendor/
```

Patches are applied in four steps:
1. Copy `patches/tt_dit/` into `vendor/` (dev_mode pipeline fixes)
2. Patch `run_docker_server.py` with dev_mode bind-mounts
3. Copy `patches/media_server_config/` into `vendor/` (constants overrides)
4. Patch `run_docker_server.py` with unconditional `constants.py` bind-mount

The `.env` in `vendor/tt-inference-server/` controls Docker container environment (including `HF_HUB_OFFLINE=1` and `TT_DIT_CACHE_DIR` for weight caching across restarts).

---

## Running tests

```bash
/usr/bin/python3 -m pytest tests/ -q   # 83 tests, all should pass
```

---

## License

Apache 2.0
