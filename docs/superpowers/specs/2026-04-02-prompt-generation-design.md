# Prompt Generation Feature — Design Spec

**Date:** 2026-04-02
**Status:** Approved

---

## Overview

An optional "Inspire me" prompt generation feature powered by a local Qwen3-0.6B model (CPU, port 8001). Users can click a button below the prompt textarea to generate a cinematic prompt appropriate for the current generation mode (video / image / animate). If the textarea already has text, that text is used as a seed for generation; otherwise a fresh prompt is generated from the model's internal word banks.

The feature is entirely optional — the main app works fine without it. The Qwen server is a separate process that users start on demand.

---

## Files

| File | Change |
|------|--------|
| `prompt_client.py` | **New** — `check_health()` and `generate_prompt()`, no GTK deps |
| `main_window.py` | Add inspire row to `ControlPanel`, prompt gen polling thread to `MainWindow`, CSS for new states |
| `README.md` | New optional section: prompt generator setup and one-time download |

Existing files `start_prompt_gen.sh`, `prompt_server.py`, and `prompts/prompt_generator.md` are already in the repo and are not modified.

---

## prompt_client.py

A thin HTTP client for the prompt generation server. No GTK imports — keeps the module testable and reusable.

```python
def check_health(base_url: str = "http://127.0.0.1:8001") -> bool:
    """Return True if the prompt gen server is up and model_ready."""

def generate_prompt(
    source: str,           # "video" | "image" | "animate"
    seed_text: str,        # existing prompt text, or "" for fresh generation
    system_prompt: str,    # full content of prompts/prompt_generator.md
    base_url: str = "http://127.0.0.1:8001",
    max_tokens: int = 150,
) -> str:
    """
    POST /v1/chat/completions to the prompt gen server.
    
    User message format:
      "{source}: {seed_text}"   — if seed_text is non-empty
      "{source}: "              — if empty (model uses its word banks)
    
    Returns the generated prompt string (stripped).
    Raises requests.RequestException on network errors.
    Raises ValueError if the response is malformed.
    """
```

The system prompt is passed in (not read inside the module) so the caller controls loading and caching.

---

## ControlPanel changes

### Inspire row (below prompt textarea)

Inserted between the prompt scroll widget and the error label:

```
[ ✨ Inspire me ]           [ ⬤ offline ]
```

The dot + label on the right reflects the current prompt gen server state:
- `⬤ offline` (muted gray) — server not running
- `⬤ starting…` (teal, pulsing) — server launched, model loading
- `⬤ ready` (green) — server up and model ready

#### States of the Inspire button

| State | Button label | Button style | Dot label |
|---|---|---|---|
| Server offline, idle | `✨ Inspire me` | normal | `⬤ offline` |
| Server offline, confirm shown | `✨ Inspire me` (disabled) | muted | `⬤ offline` |
| Server starting | `⏳ Starting…` (disabled) | teal border, pulsing | `⬤ starting…` |
| Server ready, idle | `✨ Inspire me` | normal | `⬤ ready` |
| Generating | `⏳ Generating…` (disabled) | teal border | `⬤ ready` |

#### Confirm box (shown when Inspire clicked while offline)

Drops in immediately below the inspire row (not a dialog — inline):

```
┌─────────────────────────────────────────────┐
│ Prompt generator isn't running. Start it?   │
│ (~20s warm-up on first use)                 │
│  [ ▶ Start ]  [ Not now ]                   │
└─────────────────────────────────────────────┘
```

- `▶ Start` — launches `start_prompt_gen.sh --gui`, dismisses the confirm box, transitions to "starting…" state, auto-generates once ready
- `Not now` — dismisses the confirm box, no other action

### New ControlPanel internal state

```python
self._prompt_gen_ready: bool = False         # True when port 8001 health check passes
self._prompt_gen_starting: bool = False      # True while start script is running
self._prompt_gen_generating: bool = False    # True while waiting for generate_prompt()
self._confirm_box_visible: bool = False      # True while inline confirm box is shown
self._inspire_auto_generate: bool = False    # True when user clicked Start in confirm box;
                                             # cleared after auto-generation fires once ready
```

When the user clicks `▶ Start` in the confirm box, `_inspire_auto_generate` is set to `True`.
In `set_prompt_gen_state(ready=True)`, if `_inspire_auto_generate` is `True` and the server
just became ready (transitioned from `_prompt_gen_starting`), clear `_inspire_auto_generate`
and call `_start_inspire_generation()` automatically.

### New ControlPanel methods

```python
def set_prompt_gen_state(self, ready: bool) -> None:
    """Update the inspire row dot and button sensitivity from health poll result."""

def set_prompt_gen_starting(self, starting: bool) -> None:
    """Show/hide the starting… state on the inspire row."""

def _on_inspire_clicked(self, _btn) -> None:
    """Handle Inspire button click: show confirm if offline, else start generation."""

def _on_inspire_confirm_start(self, _btn) -> None:
    """User clicked ▶ Start in confirm box — launch start_prompt_gen.sh --gui."""

def _on_inspire_confirm_cancel(self, _btn) -> None:
    """User clicked Not now — dismiss confirm box."""

def _start_inspire_generation(self) -> None:
    """Fire the background thread that calls prompt_client.generate_prompt()."""

def _on_inspire_result(self, text: str) -> None:
    """Main-thread callback: replace prompt textarea with generated text."""

def _on_inspire_error(self, msg: str) -> None:
    """Main-thread callback: restore button on generation failure."""
```

### Generation flow

1. User clicks `✨ Inspire me` (server ready)
2. `_on_inspire_clicked` → reads current textarea content as `seed_text`, reads `_model_source` as `source`
3. Button → `⏳ Generating…` (disabled)
4. Background thread calls `prompt_client.generate_prompt(source, seed_text, system_prompt)`
5. On success: `GLib.idle_add(self._on_inspire_result, text)` → replaces textarea content, restores button
6. On error: `GLib.idle_add(self._on_inspire_error, msg)` → restores button, logs to stderr

Generated text **replaces** the existing textarea content (not appended). The existing text served as the seed.

---

## MainWindow changes

### System prompt loading

At `MainWindow.__init__`, read the system prompt file once:

```python
self._prompt_gen_system_prompt: str = self._load_prompt_gen_system()

def _load_prompt_gen_system(self) -> str:
    path = Path(__file__).parent / "prompts" / "prompt_generator.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""  # feature degrades gracefully if file missing
```

### Prompt gen polling thread

A dedicated background thread mirrors the existing `_health_loop` pattern:

```python
self._pg_stop = threading.Event()
threading.Thread(
    target=self._prompt_gen_health_loop, daemon=True
).start()

def _prompt_gen_health_loop(self) -> None:
    while not self._pg_stop.wait(5.0):   # poll every 5 seconds
        ready = prompt_client.check_health()
        GLib.idle_add(self._on_prompt_gen_health, ready)

def _on_prompt_gen_health(self, ready: bool) -> None:
    self._ctrl.set_prompt_gen_state(ready)
    return False
```

Stop the thread in `do_close_request` alongside `_health_stop`:

```python
self._pg_stop.set()
```

### Passing on_start_prompt_gen to ControlPanel

`ControlPanel.__init__` gains a new callback parameter:

```python
on_start_prompt_gen,   # () -> None — called when user confirms start in inspire row
```

`MainWindow` provides:

```python
def _on_start_prompt_gen(self) -> None:
    """Launch start_prompt_gen.sh --gui in a subprocess, stream output to stderr."""
    script = Path(__file__).parent / "start_prompt_gen.sh"
    subprocess.Popen(
        [str(script), "--gui"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
```

No log streaming needed for the prompt gen server (it's fast and CPU-only — errors visible in `/tmp/tt_prompt_gen.log`).

---

## CSS additions

New classes added to `_CSS`:

```css
/* Inspire row */
.inspire-btn {
    background-color: @tt_bg_darkest;
    color: @tt_accent_light;
    border: 1px solid @tt_border;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
}
.inspire-btn:hover {
    background-color: @tt_bg_dark;
    border-color: @tt_accent;
    color: @tt_text;
}
.inspire-btn:disabled {
    color: @tt_text_muted;
    border-color: @tt_bg_dark;
}
.inspire-btn-loading {
    background-color: @tt_bg_darkest;
    color: @tt_accent;
    border: 1px solid @tt_accent;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
}
.inspire-dot {
    font-size: 9px;
    color: @tt_text_muted;
}
.inspire-dot-ready {
    font-size: 9px;
    color: #27AE60;
}
.inspire-dot-starting {
    font-size: 9px;
    color: @tt_accent;
}

/* Confirm box */
.inspire-confirm-box {
    background-color: @tt_bg_darkest;
    border: 1px solid @tt_accent;
    border-radius: 4px;
    padding: 6px 8px;
}
.inspire-confirm-btn {
    background-color: @tt_bg_dark;
    color: @tt_accent;
    border: 1px solid @tt_accent;
    border-radius: 3px;
    padding: 3px 8px;
    font-size: 11px;
}
.inspire-confirm-btn:hover {
    background-color: @tt_border;
}
```

---

## README additions

New section after the existing "Starting / stopping the inference server" section:

```markdown
## Prompt generator (optional)

The **✨ Inspire me** button in the prompt area uses a local Qwen3-0.6B model
to generate cinematic prompts. It runs entirely on CPU and does not use the TT
chips, so it coexists with a running video/image generation server.

### One-time setup

Install the Python dependencies:

```bash
pip install transformers torch accelerate
```

The model (~1.2 GB) downloads automatically from Hugging Face on first start.

### Starting the server

```bash
./start_prompt_gen.sh          # start, tail log (Ctrl-C leaves server running)
./start_prompt_gen.sh --stop   # stop
```

Or use the **✨ Inspire me** button in the app — if the server isn't running,
it will offer to start it for you.

### Quick test

```bash
curl -s http://localhost:8001/health
# → {"status":"ok","model_ready":true}
```
```

---

## Scope boundaries

**In scope:**
- `prompt_client.py` (new file)
- Inspire row in `ControlPanel` (placement B, offline behavior B1)
- Prompt gen health polling thread in `MainWindow`
- CSS classes for inspire row states
- README optional section

**Out of scope (deferred):**
- Auto-play / auto-generation mode (explicitly next feature)
- Streaming generation (server doesn't support it)
- Multiple prompt suggestions / undo
- Configurable prompt gen server URL or port
