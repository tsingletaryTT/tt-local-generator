# Prompt Generation Feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional "✨ Inspire me" button below the prompt textarea that generates a cinematic prompt using a local Qwen3-0.6B model on port 8001, with inline offline/starting/ready status and a confirm box to start the server on demand.

**Architecture:** A new `prompt_client.py` module (no GTK deps) exposes `check_health()` and `generate_prompt()`. `ControlPanel` gains an inspire row (button + status dot + confirm revealer), two new callbacks (`on_start_prompt_gen`, `on_inspire`), and methods to reflect server state. `MainWindow` adds a 5-second background health poll for port 8001, loads the system prompt file once, and owns the generation thread.

**Tech Stack:** Python 3, GTK4/PyGObject, `requests`, `Gtk.Revealer` (slide-down for confirm box), background `threading.Thread` + `GLib.idle_add` for non-GTK work.

---

## File Map

| File | Change |
|---|---|
| `prompt_client.py` | **New** — `check_health()`, `generate_prompt()` |
| `tests/test_prompt_client.py` | **New** — 9 unit tests, all mocked (no real server) |
| `main_window.py` | Modify `_CSS`, `ControlPanel.__init__`, `ControlPanel._build()`, add ControlPanel behavior methods, modify `MainWindow.__init__`, `_build_ui`, `_start_health_worker`, `do_close_request`, add MainWindow methods |
| `README.md` | Add optional "Prompt generator" section |

---

## Task 1: prompt_client.py + tests

**Files:**
- Create: `prompt_client.py`
- Create: `tests/test_prompt_client.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prompt_client.py`:

```python
"""Tests for prompt_client — mocked HTTP, no real server needed."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import requests

import prompt_client


# ── check_health ──────────────────────────────────────────────────────────────

def test_check_health_true_when_model_ready():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "model_ready": True}
    with patch("prompt_client.requests.get", return_value=mock_resp):
        assert prompt_client.check_health() is True


def test_check_health_false_when_model_not_ready():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "model_ready": False}
    with patch("prompt_client.requests.get", return_value=mock_resp):
        assert prompt_client.check_health() is False


def test_check_health_false_on_network_error():
    with patch("prompt_client.requests.get", side_effect=requests.ConnectionError()):
        assert prompt_client.check_health() is False


def test_check_health_false_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("prompt_client.requests.get", return_value=mock_resp):
        assert prompt_client.check_health() is False


# ── generate_prompt ───────────────────────────────────────────────────────────

def _mock_chat_response(content: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_generate_prompt_returns_content():
    expected = "A red fox trots through deep snow at midnight"
    with patch("prompt_client.requests.post", return_value=_mock_chat_response(expected)):
        result = prompt_client.generate_prompt("video", "fox in snow", "sys prompt")
    assert result == expected


def test_generate_prompt_strips_whitespace():
    with patch("prompt_client.requests.post", return_value=_mock_chat_response("  hello  ")):
        result = prompt_client.generate_prompt("image", "", "sys")
    assert result == "hello"


def test_generate_prompt_uses_source_prefix():
    captured = {}

    def mock_post(url, json=None, **kwargs):
        captured["json"] = json
        return _mock_chat_response("result")

    with patch("prompt_client.requests.post", side_effect=mock_post):
        prompt_client.generate_prompt("image", "portrait", "sys")

    user_msg = next(m for m in captured["json"]["messages"] if m["role"] == "user")
    assert user_msg["content"].startswith("image:")


def test_generate_prompt_raises_on_empty_content():
    with patch("prompt_client.requests.post", return_value=_mock_chat_response("")):
        with pytest.raises(ValueError, match="Empty content"):
            prompt_client.generate_prompt("video", "", "sys")


def test_generate_prompt_raises_on_no_choices():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}
    mock_resp.raise_for_status = MagicMock()
    with patch("prompt_client.requests.post", return_value=mock_resp):
        with pytest.raises(ValueError, match="No choices"):
            prompt_client.generate_prompt("video", "", "sys")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/code/tt-local-generator
python3 -m pytest tests/test_prompt_client.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'prompt_client'`

- [ ] **Step 3: Create prompt_client.py**

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
"""
Lightweight HTTP client for the tt-prompt-gen server (port 8001).

The server exposes an OpenAI-compatible chat API powered by Qwen3-0.6B on CPU.
This module has no GTK dependencies and is safe to import without a display.

Functions:
    check_health(base_url) -> bool
    generate_prompt(source, seed_text, system_prompt, base_url, max_tokens) -> str
"""
import requests

_DEFAULT_URL = "http://127.0.0.1:8001"


def check_health(base_url: str = _DEFAULT_URL) -> bool:
    """
    Return True if the prompt gen server is up and the model is loaded.

    Calls GET /health and checks the model_ready field.  Returns False on
    any network error, non-200 status, or missing model_ready field.
    """
    try:
        resp = requests.get(f"{base_url}/health", timeout=3)
        if resp.status_code == 200:
            return bool(resp.json().get("model_ready"))
        return False
    except requests.RequestException:
        return False


def generate_prompt(
    source: str,
    seed_text: str,
    system_prompt: str,
    base_url: str = _DEFAULT_URL,
    max_tokens: int = 150,
) -> str:
    """
    Generate a cinematic prompt via the Qwen3-0.6B server.

    Args:
        source:        "video", "image", or "animate" — prefixed to the user
                       message so the model knows which output format to use.
        seed_text:     Existing prompt text to use as a creative seed.  Pass ""
                       to let the model invent freely from its word banks.
        system_prompt: Full contents of prompts/prompt_generator.md.
        base_url:      URL of the prompt gen server (default: http://127.0.0.1:8001).
        max_tokens:    Maximum tokens to generate (default: 150).

    Returns:
        The generated prompt string stripped of leading/trailing whitespace.

    Raises:
        requests.RequestException: On network or HTTP errors.
        ValueError: If the server returns no choices or empty content.
    """
    user_content = f"{source}: {seed_text}"
    payload = {
        "model": "Qwen/Qwen3-0.6B",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
        "top_p": 0.9,
    }
    resp = requests.post(
        f"{base_url}/v1/chat/completions",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError(f"No choices in server response: {data}")
    content = choices[0].get("message", {}).get("content", "").strip()
    if not content:
        raise ValueError(f"Empty content in server response: {data}")
    return content
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_prompt_client.py -v
```

Expected: 9 tests PASS, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add prompt_client.py tests/test_prompt_client.py
git commit -m "feat: add prompt_client module with check_health and generate_prompt"
```

---

## Task 2: CSS additions for inspire row

**Files:**
- Modify: `main_window.py` (`_CSS` bytes literal, around line 427–438)

The `_CSS` bytes literal ends with the `.animate-inputs-title` block and then `"""`.
Add the inspire row CSS classes immediately before the closing `"""`.

- [ ] **Step 1: Read the end of the `_CSS` block to confirm the insertion point**

Read `main_window.py` lines 425–440 to confirm the last line of CSS before the closing `"""`.

Expected: the last rule is `.animate-inputs-title { color: @tt_accent; font-size: 9px; }` followed by `"""`.

- [ ] **Step 2: Insert the new CSS classes before the closing `"""`**

In `main_window.py`, find the exact text:

```
.animate-inputs-title {
    color: @tt_accent;
    font-size: 9px;
}
"""
```

Replace it with:

```
.animate-inputs-title {
    color: @tt_accent;
    font-size: 9px;
}

/* -- Inspire row (prompt generator) --------------------------------------- */
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
.inspire-confirm-box {
    background-color: @tt_bg_darkest;
    border: 1px solid @tt_accent;
    border-radius: 4px;
    padding: 6px 8px;
    margin-top: 2px;
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
"""
```

- [ ] **Step 3: Smoke-test CSS loads without error**

```bash
python3 -c "
import gi; gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from main_window import _CSS
p = Gtk.CssProvider()
p.load_from_data(_CSS)
print('CSS OK')
"
```

Expected: `CSS OK` with no warnings about unknown properties.

- [ ] **Step 4: Commit**

```bash
git add main_window.py
git commit -m "style: add inspire row CSS classes to _CSS palette"
```

---

## Task 3: ControlPanel — constructor, state variables, inspire row UI

**Files:**
- Modify: `main_window.py` — `ControlPanel.__init__` (line ~1644), `ControlPanel._build()` (line ~1840)

- [ ] **Step 1: Add `on_start_prompt_gen` and `on_inspire` parameters to `ControlPanel.__init__`**

Find the `ControlPanel.__init__` signature (starts at line ~1644):

```python
    def __init__(
        self,
        on_generate,       # (prompt, neg, steps, seed, seed_image_path, model_source, guidance_scale, ref_video_path, ref_char_path, animate_mode, model_id) -> None
        on_enqueue,        # same signature
        on_cancel,         # () -> None
        on_recover,        # () -> None
        on_start_server,   # (model_source: str) -> None
        on_stop_server,    # () -> None
        on_source_change,  # (model_source: str) -> None — called after the mode toggle switches
    ):
```

Replace with:

```python
    def __init__(
        self,
        on_generate,       # (prompt, neg, steps, seed, seed_image_path, model_source, guidance_scale, ref_video_path, ref_char_path, animate_mode, model_id) -> None
        on_enqueue,        # same signature
        on_cancel,         # () -> None
        on_recover,        # () -> None
        on_start_server,   # (model_source: str) -> None
        on_stop_server,    # () -> None
        on_source_change,  # (model_source: str) -> None — called after the mode toggle switches
        on_start_prompt_gen = None,  # () -> None — launch start_prompt_gen.sh --gui
        on_inspire = None,           # (source: str, seed_text: str) -> None — start generation thread
    ):
```

- [ ] **Step 2: Store the new callbacks and add state variables**

Inside `__init__`, find the existing assignment block (around line 1654–1674):

```python
        self._on_generate = on_generate
        self._on_enqueue = on_enqueue
        self._on_cancel = on_cancel
        self._on_recover = on_recover
        self._on_start_server = on_start_server
        self._on_stop_server = on_stop_server
        self._on_source_change = on_source_change
```

Replace with:

```python
        self._on_generate = on_generate
        self._on_enqueue = on_enqueue
        self._on_cancel = on_cancel
        self._on_recover = on_recover
        self._on_start_server = on_start_server
        self._on_stop_server = on_stop_server
        self._on_source_change = on_source_change
        self._on_start_prompt_gen = on_start_prompt_gen or (lambda: None)
        self._on_inspire = on_inspire or (lambda s, t: None)
        # ── Prompt gen server state ───────────────────────────────────────────
        self._prompt_gen_ready: bool = False      # True when port 8001 health check passes
        self._prompt_gen_starting: bool = False   # True while start_prompt_gen.sh is running
        self._prompt_gen_generating: bool = False # True while waiting for generate_prompt()
        self._confirm_box_visible: bool = False   # True while inline confirm box is shown
        # Source + seed captured at click time for auto-generate after server starts
        self._inspire_pending_source: "str | None" = None
        self._inspire_pending_seed: str = ""
```

- [ ] **Step 3: Add inspire row + confirm revealer in `_build()` after prompt error label**

In `_build()`, find:

```python
        self._prompt_error_lbl = Gtk.Label(label="Prompt cannot be empty.")
        self._prompt_error_lbl.add_css_class("prompt-error")
        self._prompt_error_lbl.set_halign(Gtk.Align.START)
        self._prompt_error_lbl.set_visible(False)
        self.append(self._prompt_error_lbl)

        # ── Prompt component chips ────────────────────────────────────────────
```

Replace the comment line `# ── Prompt component chips` (and everything after through `self._chips_scroll`) only if they belong to the chips section — **do not remove the chips code**. Instead, **insert the following block between the error label append and the chips comment**:

```python
        self._prompt_error_lbl = Gtk.Label(label="Prompt cannot be empty.")
        self._prompt_error_lbl.add_css_class("prompt-error")
        self._prompt_error_lbl.set_halign(Gtk.Align.START)
        self._prompt_error_lbl.set_visible(False)
        self.append(self._prompt_error_lbl)

        # ── Inspire row ───────────────────────────────────────────────────────
        # "✨ Inspire me" button + status dot for the prompt gen server (port 8001).
        inspire_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._inspire_btn = Gtk.Button(label="✨ Inspire me")
        self._inspire_btn.add_css_class("inspire-btn")
        self._inspire_btn.set_tooltip_text(
            "Generate a cinematic prompt using the local Qwen3-0.6B model.\n"
            "If the prompt box already has text, it is used as a creative seed.\n"
            "Requires: ./start_prompt_gen.sh  (CPU-only, ~1.2 GB one-time download)"
        )
        self._inspire_btn.connect("clicked", self._on_inspire_clicked)
        inspire_row.append(self._inspire_btn)

        _inspire_spacer = Gtk.Box()
        _inspire_spacer.set_hexpand(True)
        inspire_row.append(_inspire_spacer)

        self._inspire_dot_lbl = Gtk.Label(label="⬤ offline")
        self._inspire_dot_lbl.add_css_class("inspire-dot")
        inspire_row.append(self._inspire_dot_lbl)
        self.append(inspire_row)

        # Confirm box — hidden; slides in when Inspire is clicked while server is offline
        self._inspire_confirm_revealer = Gtk.Revealer()
        self._inspire_confirm_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self._inspire_confirm_revealer.set_transition_duration(150)
        self._inspire_confirm_revealer.set_reveal_child(False)
        _confirm_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        _confirm_box.add_css_class("inspire-confirm-box")
        _confirm_msg = Gtk.Label(
            label="Prompt generator isn't running. Start it now? (~20s warm-up)"
        )
        _confirm_msg.set_xalign(0)
        _confirm_msg.set_wrap(True)
        _confirm_box.append(_confirm_msg)
        _confirm_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._inspire_start_btn = Gtk.Button(label="▶ Start")
        self._inspire_start_btn.add_css_class("inspire-confirm-btn")
        self._inspire_start_btn.connect("clicked", self._on_inspire_confirm_start)
        _confirm_btns.append(self._inspire_start_btn)
        _inspire_cancel_btn = Gtk.Button(label="Not now")
        _inspire_cancel_btn.connect("clicked", self._on_inspire_confirm_cancel)
        _confirm_btns.append(_inspire_cancel_btn)
        _confirm_box.append(_confirm_btns)
        self._inspire_confirm_revealer.set_child(_confirm_box)
        self.append(self._inspire_confirm_revealer)

        # ── Prompt component chips ────────────────────────────────────────────
```

- [ ] **Step 4: Smoke-test app opens with inspire row visible**

```bash
/usr/bin/python3 main.py &
sleep 3; kill %1
echo "OK"
```

Expected: app opens, no Python traceback. The inspire row appears below the prompt textarea with "⬤ offline" dot.

- [ ] **Step 5: Commit**

```bash
git add main_window.py
git commit -m "feat: add inspire row UI to ControlPanel (button + status dot + confirm revealer)"
```

---

## Task 4: ControlPanel — behavior methods

**Files:**
- Modify: `main_window.py` — add methods to `ControlPanel` class

Add all the following methods to `ControlPanel`. A good insertion point is immediately after the `_on_prompt_changed` method (search for `def _on_prompt_changed`).

- [ ] **Step 1: Add `set_prompt_gen_state`**

```python
    def set_prompt_gen_state(self, ready: bool) -> None:
        """
        Update the inspire row dot and button sensitivity from the health poll result.

        Called from the main thread via GLib.idle_add.  Handles the auto-generate
        flow: if the server just became ready after the user clicked "▶ Start" in
        the confirm box, fires the pending generation automatically.
        """
        was_starting = self._prompt_gen_starting
        self._prompt_gen_ready = ready

        if ready:
            self._prompt_gen_starting = False
            # Update dot to green "ready"
            self._inspire_dot_lbl.set_label("⬤ ready")
            for cls in ("inspire-dot", "inspire-dot-starting"):
                self._inspire_dot_lbl.remove_css_class(cls)
            self._inspire_dot_lbl.add_css_class("inspire-dot-ready")
            # Restore button if not mid-generation
            if not self._prompt_gen_generating:
                self._inspire_btn.set_label("✨ Inspire me")
                self._inspire_btn.remove_css_class("inspire-btn-loading")
                self._inspire_btn.add_css_class("inspire-btn")
                self._inspire_btn.set_sensitive(True)
            # Auto-generate if pending from the confirm-start flow
            if was_starting and self._inspire_pending_source is not None:
                source = self._inspire_pending_source
                seed = self._inspire_pending_seed
                self._inspire_pending_source = None
                self._inspire_pending_seed = ""
                self._trigger_inspire(source, seed)
        elif not self._prompt_gen_starting:
            # Server is offline and not actively starting — show offline state
            self._inspire_dot_lbl.set_label("⬤ offline")
            for cls in ("inspire-dot-ready", "inspire-dot-starting"):
                self._inspire_dot_lbl.remove_css_class(cls)
            self._inspire_dot_lbl.add_css_class("inspire-dot")
            if not self._prompt_gen_generating:
                self._inspire_btn.set_label("✨ Inspire me")
                self._inspire_btn.remove_css_class("inspire-btn-loading")
                self._inspire_btn.add_css_class("inspire-btn")
                self._inspire_btn.set_sensitive(True)
```

- [ ] **Step 2: Add `set_prompt_gen_starting`**

```python
    def set_prompt_gen_starting(self, starting: bool) -> None:
        """Show/hide the starting… state on the inspire row button and dot."""
        self._prompt_gen_starting = starting
        if starting:
            self._inspire_dot_lbl.set_label("⬤ starting…")
            for cls in ("inspire-dot", "inspire-dot-ready"):
                self._inspire_dot_lbl.remove_css_class(cls)
            self._inspire_dot_lbl.add_css_class("inspire-dot-starting")
            self._inspire_btn.set_label("⏳ Starting…")
            self._inspire_btn.remove_css_class("inspire-btn")
            self._inspire_btn.add_css_class("inspire-btn-loading")
            self._inspire_btn.set_sensitive(False)
```

- [ ] **Step 3: Add `_on_inspire_clicked`, `_on_inspire_confirm_start`, `_on_inspire_confirm_cancel`**

```python
    def _on_inspire_clicked(self, _btn) -> None:
        """Handle Inspire button click: show confirm box if offline, else generate."""
        if not self._prompt_gen_ready:
            # Reveal inline confirm box; disable button until user decides
            self._inspire_confirm_revealer.set_reveal_child(True)
            self._confirm_box_visible = True
            self._inspire_btn.set_sensitive(False)
        else:
            source = self._model_source
            seed_text = self._prompt_buf.get_text(
                self._prompt_buf.get_start_iter(),
                self._prompt_buf.get_end_iter(),
                False,
            ).strip()
            self._trigger_inspire(source, seed_text)

    def _on_inspire_confirm_start(self, _btn) -> None:
        """User clicked ▶ Start in the confirm box — launch server and set auto-generate."""
        self._inspire_confirm_revealer.set_reveal_child(False)
        self._confirm_box_visible = False
        # Capture source + seed at click time so auto-generate uses the right values
        self._inspire_pending_source = self._model_source
        self._inspire_pending_seed = self._prompt_buf.get_text(
            self._prompt_buf.get_start_iter(),
            self._prompt_buf.get_end_iter(),
            False,
        ).strip()
        self.set_prompt_gen_starting(True)
        self._on_start_prompt_gen()

    def _on_inspire_confirm_cancel(self, _btn) -> None:
        """User clicked Not now — dismiss confirm box, restore button."""
        self._inspire_confirm_revealer.set_reveal_child(False)
        self._confirm_box_visible = False
        self._inspire_btn.set_sensitive(True)
```

- [ ] **Step 4: Add `_trigger_inspire`, `set_inspire_result`, `set_inspire_error`**

```python
    def _trigger_inspire(self, source: str, seed_text: str) -> None:
        """Set loading state and call on_inspire(source, seed_text) to fire the thread."""
        self._prompt_gen_generating = True
        self._inspire_btn.set_label("⏳ Generating…")
        self._inspire_btn.remove_css_class("inspire-btn")
        self._inspire_btn.add_css_class("inspire-btn-loading")
        self._inspire_btn.set_sensitive(False)
        self._on_inspire(source, seed_text)

    def set_inspire_result(self, text: str) -> None:
        """Called on main thread when generation succeeds — replace textarea content."""
        self._prompt_gen_generating = False
        self._prompt_buf.set_text(text)
        self._inspire_btn.set_label("✨ Inspire me")
        self._inspire_btn.remove_css_class("inspire-btn-loading")
        self._inspire_btn.add_css_class("inspire-btn")
        self._inspire_btn.set_sensitive(True)

    def set_inspire_error(self, msg: str) -> None:
        """Called on main thread when generation fails — restore button state."""
        self._prompt_gen_generating = False
        self._inspire_btn.set_label("✨ Inspire me")
        self._inspire_btn.remove_css_class("inspire-btn-loading")
        self._inspire_btn.add_css_class("inspire-btn")
        self._inspire_btn.set_sensitive(True)
```

- [ ] **Step 5: Smoke-test inspire row behavior with server offline**

```bash
/usr/bin/python3 main.py &
```

Steps:
1. Confirm inspire row is visible below the prompt textarea
2. Click "✨ Inspire me" → confirm box should drop in below the row
3. Click "Not now" → confirm box should collapse, button re-enables
4. Click "✨ Inspire me" again → confirm box appears again
5. Kill the app

```bash
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add main_window.py
git commit -m "feat: add inspire row behavior methods to ControlPanel"
```

---

## Task 5: MainWindow — wiring, health loop, generation thread

**Files:**
- Modify: `main_window.py` — `MainWindow.__init__`, `_build_ui`, `do_close_request`; add methods; add import

- [ ] **Step 1: Add `import prompt_client` to the imports block**

In `main_window.py`, find the existing import block (around line 36–39):

```python
from api_client import APIClient
from chip_config import load_chips as _load_chips
from history_store import GenerationRecord, HistoryStore
from worker import AnimateGenerationWorker, GenerationWorker, ImageGenerationWorker
```

Replace with:

```python
from api_client import APIClient
from chip_config import load_chips as _load_chips
from history_store import GenerationRecord, HistoryStore
from worker import AnimateGenerationWorker, GenerationWorker, ImageGenerationWorker
import prompt_client
```

- [ ] **Step 2: Add `_pg_stop` state and system-prompt loading to `MainWindow.__init__`**

Find the end of `MainWindow.__init__` (around line 2835–2839):

```python
        self._auto_tab_switched = False  # True after first model detection auto-switch

        self._build_ui()
        self._load_history()
        self._start_health_worker()
```

Replace with:

```python
        self._auto_tab_switched = False  # True after first model detection auto-switch
        self._pg_stop: Optional[threading.Event] = None  # set when prompt gen poll starts
        self._prompt_gen_system_prompt: str = self._load_prompt_gen_system()

        self._build_ui()
        self._load_history()
        self._start_health_worker()
        self._start_prompt_gen_health_worker()
```

- [ ] **Step 3: Add `_load_prompt_gen_system` method to MainWindow**

Add this method near `_start_health_worker` (around line 2996):

```python
    def _load_prompt_gen_system(self) -> str:
        """
        Read the system prompt for the Qwen prompt generator from disk.

        Returns the file contents as a string.  Returns "" if the file is
        missing so the feature degrades gracefully (the model will still
        generate something, just without the cinematic mad-libs guidance).
        """
        path = Path(__file__).parent / "prompts" / "prompt_generator.md"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""
```

- [ ] **Step 4: Add the prompt gen health worker methods**

Add immediately after `_load_prompt_gen_system`:

```python
    def _start_prompt_gen_health_worker(self) -> None:
        """Start the background thread that polls the prompt gen server on port 8001."""
        self._pg_stop = threading.Event()
        threading.Thread(
            target=self._prompt_gen_health_loop, daemon=True
        ).start()

    def _prompt_gen_health_loop(self) -> None:
        """
        Runs on background thread.  Polls the prompt gen server every 5 seconds
        and posts the result to the main thread via GLib.idle_add.
        """
        while not self._pg_stop.wait(5.0):
            ready = prompt_client.check_health()
            # THREADING: must not touch GTK widgets here — post to main thread
            GLib.idle_add(self._on_prompt_gen_health, ready)

    def _on_prompt_gen_health(self, ready: bool) -> bool:
        """Runs on main thread (called by GLib.idle_add)."""
        self._controls.set_prompt_gen_state(ready)
        return False  # one-shot idle callback
```

- [ ] **Step 5: Add `_on_start_prompt_gen`, `_on_inspire`, `_on_inspire_result`, `_on_inspire_error`**

Add these methods near the other server-start methods (around line 3107):

```python
    def _on_start_prompt_gen(self) -> None:
        """
        Launch start_prompt_gen.sh --gui in the background.

        Runs silently — no log streaming.  The health poll on port 8001 will
        detect when the server is ready.  Users can watch /tmp/tt_prompt_gen.log
        for details.
        """
        script = Path(__file__).parent / "start_prompt_gen.sh"
        subprocess.Popen(
            [str(script), "--gui"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

    def _on_inspire(self, source: str, seed_text: str) -> None:
        """
        Start a prompt generation job in a background thread.

        Called by ControlPanel._trigger_inspire() via the on_inspire callback.
        Posts the result back to ControlPanel on the main thread.
        """
        system_prompt = self._prompt_gen_system_prompt

        def run():
            try:
                text = prompt_client.generate_prompt(source, seed_text, system_prompt)
                GLib.idle_add(self._on_inspire_result, text)
            except Exception as e:
                GLib.idle_add(self._on_inspire_error, str(e))

        threading.Thread(target=run, daemon=True).start()

    def _on_inspire_result(self, text: str) -> bool:
        """Runs on main thread — forward generated prompt text to ControlPanel."""
        self._controls.set_inspire_result(text)
        return False

    def _on_inspire_error(self, msg: str) -> bool:
        """Runs on main thread — log error and restore ControlPanel inspire button."""
        print(f"[tt-gen] Prompt generation error: {msg}", file=sys.stderr)
        self._controls.set_inspire_error(msg)
        return False
```

- [ ] **Step 6: Pass new callbacks to `ControlPanel` in `_build_ui`**

Find the `ControlPanel(...)` constructor call in `_build_ui` (around line 2855):

```python
        self._controls = ControlPanel(
            on_generate=self._on_generate,
            on_enqueue=self._on_enqueue,
            on_cancel=self._on_cancel,
            on_recover=self._on_recover,
            on_start_server=self._on_start_server,
            on_stop_server=self._on_stop_server,
            on_source_change=self._on_source_change,
        )
```

Replace with:

```python
        self._controls = ControlPanel(
            on_generate=self._on_generate,
            on_enqueue=self._on_enqueue,
            on_cancel=self._on_cancel,
            on_recover=self._on_recover,
            on_start_server=self._on_start_server,
            on_stop_server=self._on_stop_server,
            on_source_change=self._on_source_change,
            on_start_prompt_gen=self._on_start_prompt_gen,
            on_inspire=self._on_inspire,
        )
```

- [ ] **Step 7: Stop the prompt gen poll thread on window close**

Find `do_close_request` (around line 3357):

```python
    def do_close_request(self) -> bool:
        self._health_stop.set()
        if self._worker_gen:
            self._worker_gen.cancel()
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
        return False  # allow close
```

Replace with:

```python
    def do_close_request(self) -> bool:
        self._health_stop.set()
        if self._pg_stop:
            self._pg_stop.set()
        if self._worker_gen:
            self._worker_gen.cancel()
        if self._server_proc and self._server_proc.poll() is None:
            self._server_proc.terminate()
        return False  # allow close
```

- [ ] **Step 8: Smoke-test full flow**

```bash
/usr/bin/python3 main.py &
```

Steps:
1. Confirm app opens without traceback
2. "⬤ offline" dot appears in inspire row
3. Click "✨ Inspire me" → confirm box drops in
4. Click "Not now" → confirm box hides

Now start the prompt gen server in another terminal and wait for it to be ready:
```bash
./start_prompt_gen.sh
# Wait for: ✓ Prompt generator ready at http://127.0.0.1:8001
```

Back in the app:
5. Dot should change to "⬤ ready" (within ~5s of health poll)
6. Click "✨ Inspire me" → button shows "⏳ Generating…"
7. After ~10–30s the prompt textarea fills with a generated prompt
8. Button restores to "✨ Inspire me"
9. Type some text in the prompt, click Inspire again → generated prompt uses your text as seed

```bash
./start_prompt_gen.sh --stop
kill %1
```

- [ ] **Step 9: Commit**

```bash
git add main_window.py
git commit -m "feat: wire prompt gen health loop and generation thread into MainWindow"
```

---

## Task 6: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add prompt generator section after the Architecture table**

Find the Architecture table section in README.md, which ends with:

```markdown
| `assets/` | Bundled assets: `tenstorrent.png` icon, `ai.tenstorrent.tt-video-gen.desktop` |

## License
```

Insert the following section between the Architecture table and the License section:

```markdown
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
```

- [ ] **Step 2: Verify the README renders correctly**

```bash
python3 -c "
import re
text = open('README.md').read()
assert '## Prompt generator (optional)' in text
assert 'start_prompt_gen.sh' in text
assert 'prompt_client.py' in text
print('README OK')
"
```

Expected: `README OK`

- [ ] **Step 3: Run all non-GTK tests to confirm no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass (test_chip_config.py + test_model_attribution.py + test_prompt_client.py).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add optional prompt generator section to README"
```

---

## Verification (end-to-end)

After all tasks:

```bash
python3 -m pytest tests/ -v                # all tests pass
/usr/bin/python3 main.py                   # full smoke test
```

Checklist:
- [ ] All tests in `tests/` pass
- [ ] App opens; inspire row shows "⬤ offline" dot below the prompt textarea
- [ ] Clicking Inspire while offline → confirm box slides in
- [ ] Clicking "Not now" → confirm box collapses, button re-enables
- [ ] Start prompt gen server → dot transitions to "⬤ starting…" then "⬤ ready" within 5s of health poll
- [ ] Clicking Inspire while ready → button shows "⏳ Generating…", result replaces textarea
- [ ] Typing seed text, clicking Inspire → generated prompt is seeded by the existing text
- [ ] Source toggle (Video/Image) reflected in generated prompt style
- [ ] Closing the app terminates the prompt gen health poll thread cleanly
- [ ] No regressions in generate/queue/server-start/gallery flows
