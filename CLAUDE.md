# tt-local-generator — developer notes

## Running the app

```bash
./tt-gen                                            # recommended launcher
/usr/bin/python3 app/main.py [--server http://localhost:8000]  # direct
```

Use the **system** python3 (`/usr/bin/python3`), not a venv. GTK4 bindings
(`python3-gi`) are installed as system packages and are invisible inside venvs.

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0  # if missing
```

## Starting / stopping the inference server

From the GUI, use the **Servers ▾** toolbar dropdown or the **▶ Start** / **■ Stop**
buttons in the server control row. Start is context-aware: Video tab starts
`start_wan_qb2.sh` (QB2/P300x2) or `start_mochi.sh`; Animate tab starts
`start_animate.sh`; Image tab starts `start_flux.sh`. Script output streams into
a collapsible log panel that closes when the health check confirms the server is ready.

From the terminal (all scripts are in `bin/`):

```bash
cd ~/code/tt-local-generator
./bin/start_wan_qb2.sh         # Wan2.2-T2V on QB2 (P300x2) — default
./bin/start_wan_qb2.sh --stop  # stop the running server container
./bin/start_wan.sh             # Wan2.2-T2V on P150x4
./bin/start_mochi.sh           # Mochi-1 on QB2
./bin/start_animate.sh         # Wan2.2-Animate-14B (CPU/CUDA Phase 1)
./bin/start_flux.sh            # FLUX.1-dev image server
./bin/start_prompt_gen.sh      # Qwen3-0.6B prompt server (CPU, port 8001)
```

Or via the CLI:

```bash
./tt-ctl start wan2.2          # non-blocking; same as start_wan_qb2.sh --gui
./tt-ctl stop  wan2.2
./tt-ctl start all             # wan2.2 + prompt-server
./tt-ctl servers               # live health of every managed service
```

All scripts accept `--gui` (non-blocking, skips the interactive tail).
The server is ready when the log prints `Application startup complete`.

### Animate mode (Wan2.2-Animate-14B)

The **💃 Animate** source toggle activates Wan2.2-Animate-14B, a video-to-video
character animation model. Unlike the text-to-video T2V mode, it requires:

- **Motion video** — an MP4 supplying the motion pattern
- **Character image** — PNG/JPG of the character to animate
- **Mode** — `animation` (character mimics the motion) or `replacement` (character
  replaces the person in the video)

The text prompt is optional (style guidance only). `start_animate.sh` binds the
modified `tt-media-server` files from `~/code/tt-inference-server/tt-media-server/`
into the container and upgrades `diffusers>=0.34.0` before starting uvicorn
(Phase 1: Diffusers CPU/CUDA path — TT hardware support pending).

## Directory layout

All Python source lives in `app/`, shell scripts in `bin/`.

```
tt-local-generator/
  app/                   ← Python source
  bin/                   ← shell scripts (start_*.sh, apply_patches.sh)
  patches/               ← hotpatch files applied by bin/apply_patches.sh
  vendor/                ← shallow clone of tt-inference-server (gitignored)
  docker/                ← Docker image archive (Git LFS, ~7.4 GB)
  tests/                 ← pytest test suite (83 tests)
  tt-gen                 ← GUI launcher
  tt-ctl                 ← CLI (status, history, start/stop services)
```

## Architecture

| File | Purpose |
|---|---|
| `app/main.py` | `Gtk.Application` entry point |
| `app/main_window.py` | All GTK4 widgets and `MainWindow` |
| `app/worker.py` | `GenerationWorker` — pure Python, no GUI imports |
| `app/api_client.py` | HTTP client for the inference server |
| `app/server_manager.py` | Start/stop/health for all managed services (no GTK) |
| `app/history_store.py` | Persistent JSON history + file path management |

`worker.py`, `api_client.py`, `server_manager.py`, and `history_store.py` have
**zero GUI dependencies** — keep them that way.

## Server management (`server_manager.py`)

`app/server_manager.py` is the single source of truth for all managed services.
It is imported by both `tt-ctl` and `main_window.py`. Add new services there by
adding a `ServerDef` to `SERVERS`. Current services: `wan2.2`, `mochi`, `flux`,
`animate`, `prompt-server`. The key `"all"` starts the recommended set
(`wan2.2` + `prompt-server`).

```python
from server_manager import start, stop, restart, health, status_all, SERVERS

start("wan2.2")           # launch Wan2.2 server (non-blocking --gui mode)
stop("prompt-server")     # send --stop to the prompt-gen script
health("wan2.2")          # {"wan2.2": True/False}
status_all()              # {"wan2.2": True, "prompt-server": False, ...}
```

Path resolution: `_REPO_ROOT = Path(__file__).resolve().parent.parent` (app/ → repo root).
All script paths are `_BIN / sdef.script` where `_BIN = _REPO_ROOT / "bin"`.

## GTK threading discipline (CRITICAL)

GTK is strictly single-threaded. **Never call any GTK method from a background
thread.** Doing so causes silent data corruption or hard crashes that are
difficult to debug.

### The rule

Every UI update from a worker thread must be posted to the main thread via:

```python
GLib.idle_add(callback, *args)
```

`idle_add` schedules `callback(*args)` to run on the GLib main loop (main
thread) at the next idle moment. The callback **must return `False`** (or
`GLib.SOURCE_REMOVE`) to run once; return `True` to keep repeating.

### Pattern used in this app

`GenerationWorker.run_with_callbacks()` takes three plain Python callables.
`MainWindow` wraps each one in `GLib.idle_add` when it passes them in:

```python
gen.run_with_callbacks(
    on_progress=lambda msg: GLib.idle_add(self._on_progress, msg, pending),
    on_finished=lambda rec: GLib.idle_add(self._on_finished, rec),
    on_error=lambda msg:    GLib.idle_add(self._on_error, msg),
)
```

The `_on_progress`, `_on_finished`, `_on_error` methods then touch widgets
freely because they run on the main thread.

### GLib.timeout_add

`PendingCard` uses `GLib.timeout_add(1000, self._tick)` for the elapsed-time
counter. This fires on the main thread — no `idle_add` needed inside `_tick`.
Cancel it with `GLib.source_remove(timer_id)` when the card is replaced.

### Health worker

The health-check loop uses `threading.Thread` + `daemon=True`. It posts results
via `GLib.idle_add(self._on_health_result, ready)`. The `_health_stop` event
lets `do_close_request` cleanly signal the thread to exit.

## FileDialog (GTK4 async API)

GTK4's `Gtk.FileDialog` is async — it takes a callback, not a return value:

```python
dlg = Gtk.FileDialog()
dlg.open(parent_window, cancellable, callback)  # returns immediately

def callback(dlg, result):
    try:
        gfile = dlg.open_finish(result)
    except Exception:
        return   # user cancelled
    path = gfile.get_path()
```

Always wrap `open_finish` / `save_finish` in try/except — they raise if the
user cancels.

## Queue system

`MainWindow._queue` is a `list[_QueueItem]`. After `_on_finished` runs,
`_start_next_queued()` pops the front item and calls `_on_generate()` directly.
`ControlPanel.update_queue_display()` rebuilds the visible list; call it from
the main thread only (always safe since queue mutations happen in response to
button clicks or `_on_finished`).

## PyGObject gotchas

- **No `set_data`/`get_data` on widgets**: PyGObject deliberately blocks GObject's
  C-level data methods. Store arbitrary Python values as plain attributes instead:
  ```python
  cb.job = job_dict   # yes
  cb.set_data("job", job_dict)  # RuntimeError
  ```

## Assets

`app/assets/` contains:
- `tenstorrent.png` — 32×32 app icon (pulled from tenstorrent.com/favicon.ico)
- `ai.tenstorrent.tt-video-gen.desktop` — XDG desktop entry for GNOME/KDE launchers

`setup_ubuntu.sh` copies both into the correct XDG locations automatically.
To install manually:
```bash
cp app/assets/tenstorrent.png ~/.local/share/icons/hicolor/32x32/apps/ai.tenstorrent.tt-video-gen.png
cp app/assets/ai.tenstorrent.tt-video-gen.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications
```

## Video hover / looping

`Gtk.Video.set_loop(True)` is unreliable when playback is driven by calling
`get_media_stream().play()` directly — it bypasses GTK's internal
`notify::ended` → seek(0) → play() loop restart logic.

**Fix in place**: `GenerationCard._play_hover_stream()` lazily connects a
`notify::ended` handler (`_on_stream_ended`) the first time a stream is played,
then manually seeks to 0 and restarts. `_loop_connected` guards against double-
connecting.

The stream itself is created lazily by GStreamer and `get_media_stream()` returns
`None` until the `Gtk.Video` widget has been realized. `_play_hover_stream()`
retries via `GLib.timeout_add(100, ...)` if the stream is not yet available.

## GTK Application single-instance behaviour

`Gtk.Application` uses D-Bus to enforce a single instance per `application_id`
by default. If any process has already registered `ai.tenstorrent.tt-video-gen`
on the session bus, a second `./tt-gen` invocation silently exits (code 0)
without ever firing `activate`.

**Fix in place**: `main.py` calls `app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)`
so every launch is independent. If the app is not opening, also check for a
stale process: `pgrep -a python3 | grep main.py`.

## Stale .pyc cache

If the app crashes with a traceback pointing to a line number that doesn't
match the source, the bytecode cache is stale (e.g. from an earlier version).
Clear it with:
```bash
find ~/code/tt-local-generator/app -name "*.pyc" -delete
find ~/code/tt-local-generator/app -name "__pycache__" -type d -exec rm -rf {} +
```

## Running tests

```bash
/usr/bin/python3 -m pytest tests/ -q   # 83 tests, all should pass
```

Tests are in `tests/` at repo root. Each file does `sys.path.insert(0, str(Path(__file__).parent.parent / "app"))` to import from `app/`. Tests mock all subprocess and network calls.

## Vendored `tt-inference-server`

`vendor/tt-inference-server/` is a shallow git clone of the upstream repo (gitignored due to 143 GB working tree). The pinned commit SHA is in `vendor/VENDOR_SHA`.

```bash
cat vendor/VENDOR_SHA            # see what's pinned
./bin/apply_patches.sh           # apply patches/ to vendor/
```

The `.env` file at `vendor/tt-inference-server/.env` is passed to Docker containers via `--env-file`. Key variables:
- `TT_DIT_CACHE_DIR` — caches compiled TT weights across container restarts (~66 GB after first run)
- `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` — prevents HF network access during startup (weights are bind-mounted from host cache)

The `patches/` directory contains:
- `patches/media_server_config/config/constants.py` — overrides P300X2 device config, request timeouts
- `patches/tt_dit/` — pipeline fixes (bind-mounted only in dev_mode)

## Prompt generator

A three-tier algorithmic prompt generator lives alongside the UI. It runs
independently of the video server and works even when no TT hardware is
available.

### Files

| File | Purpose |
|---|---|
| `app/generate_prompt.py` | CLI generator — algo → Markov → LLM polish |
| `app/word_banks.py` | All word banks as Python lists + sampling helpers |
| `app/prompt_server.py` | FastAPI server exposing Qwen3-0.6B on port 8001 |
| `bin/start_prompt_gen.sh` | Start/stop the prompt server |
| `app/prompts/prompt_generator.md` | System prompt for interactive LLM use |
| `app/prompts/markov_seed.txt` | Seed corpus for the Markov chain (tagged by type) |
| `app/prompts/markov_output.txt` | Accumulate good outputs here to grow the corpus |

### Three-tier design

**Tier 1 — Algorithmic** (`--mode algo`, always available):
`word_banks.py` contains every category as a Python list. `generate_prompt.py`
calls `random.choice()` on each slot independently. Selection happens in code,
not by the LLM, so diversity is guaranteed regardless of model size.

**Tier 2 — Markov** (`--mode markov`, requires `markovify`):
Trained on `prompts/markov_seed.txt` (and `markov_output.txt` if it exists).
Produces novel sentence-level recombinations — useful for unexpected register
collisions. Falls back to algo if the corpus is too small or markovify isn't
installed.

**Tier 3 — LLM polish** (`--enhance`, default on):
Sends the tier-1/2 slug to Qwen3-0.6B (port 8001) with a short polishing
prompt. The LLM only makes the output flow naturally — it does not re-select
elements. Falls back gracefully (returns the raw slug) if the server is down.

### CLI usage

```bash
# Default: algo + LLM polish, video type
python3 app/generate_prompt.py

# Markov mode, image type
python3 app/generate_prompt.py --type image --mode markov

# Algo only, no LLM, five prompts
python3 app/generate_prompt.py --count 5 --no-enhance

# Plain text output (no JSON wrapper)
python3 app/generate_prompt.py --raw

# All types
python3 app/generate_prompt.py --type video    # for Wan2.2 / Mochi
python3 app/generate_prompt.py --type image    # for FLUX / SD
python3 app/generate_prompt.py --type animate  # for Wan2.2-Animate
```

### JSON output schema

```json
{
  "prompt": "Final polished prompt string",
  "type":   "video" | "image" | "animate",
  "source": "llm" | "markov" | "algo",
  "slug":   "Raw pre-polish slug (always present)"
}
```

### Starting the prompt server

```bash
./bin/start_prompt_gen.sh          # start in background, wait for ready
./bin/start_prompt_gen.sh --stop   # stop
./bin/start_prompt_gen.sh --gui    # start silently (no tail, for GUI use)
# Or: ./tt-ctl start prompt-server
```

The server loads Qwen3-0.6B on CPU (~2.9 GB RSS, ~19 tok/s on Ryzen 7 9700X).
It runs on port 8001 and does not touch the TT chips, so it coexists with any
video generation server on port 8000.

Health check: `curl -s http://localhost:8001/health`
→ `{"status":"ok","model_ready":true}`

### Wiring into the UI

The generator is a standalone subprocess — the UI calls it and parses JSON.

**Minimal integration** (one prompt on demand):

```python
import subprocess, json

def generate_prompt(prompt_type="video", mode="markov"):
    result = subprocess.run(
        [
            "python3",
            "/home/ttuser/code/tt-local-generator/app/generate_prompt.py",
            "--type", prompt_type,
            "--mode", mode,
        ],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)["prompt"]
```

**Threading** — run the subprocess in a background thread (not the GTK main
thread). Post the result back with `GLib.idle_add` per the GTK threading rule
above:

```python
import threading
from gi.repository import GLib

def _fetch_prompt_async(prompt_entry, prompt_type="video"):
    def worker():
        prompt = generate_prompt(prompt_type)
        if prompt:
            GLib.idle_add(prompt_entry.set_text, prompt)
    threading.Thread(target=worker, daemon=True).start()
```

**Auto-start the server** (optional): call `start_prompt_gen.sh --gui` from the
app startup sequence (same pattern as the video server). Poll `/health` until
`model_ready` is true before enabling the "✨ Generate prompt" button.

**Prompt type mapping**:

| UI tab / source | `--type` |
|---|---|
| Video (Wan2.2, Mochi) | `video` |
| Image (FLUX, SD) | `image` |
| Animate (Wan2.2-Animate) | `animate` |

### Growing the Markov corpus

Append good generated prompts to `prompts/markov_output.txt` in the same
tagged format (`video|...`, `image|...`, `animate|...`). The model is rebuilt
fresh on each `generate_prompt.py` run, so additions take effect immediately.
This file is intentionally gitignored — it accumulates machine-specific history.

### Extending the word banks

Edit `word_banks.py` directly — add entries to any list. More unusual / specific
entries outperform common ones (the model anchors to surprising items). After
editing, the changes take effect on the next `generate_prompt.py` call with no
restart needed. The `prompts/prompt_generator.md` system prompt is separate and
used only for interactive LLM chat (not by `generate_prompt.py`).

---

## Known issues / history

- **ffmpeg stdin hang**: ffmpeg inherited terminal stdin from the process and
  blocked waiting for `[q]`. Fixed by passing `stdin=subprocess.DEVNULL` in
  `_extract_thumbnail`. Also add `-update 1` to avoid image-sequence warnings.

- **Inference server interactive prompt**: `setup_host.py` globs snapshot root
  for `model*.safetensors`; Wan2.2 weights live in subdirectories so the check
  always fails and prompts interactively. Fixed in `start_wan.sh` by setting
  `MODEL_SOURCE=huggingface` and `JWT_SECRET` env vars.

- **Wrong entry point**: the correct entry is `python3 run.py` in the
  `tt-inference-server` repo, not `python3 -m workflows.run_workflows`
  (that module imports `benchmarking` which isn't on the path).
