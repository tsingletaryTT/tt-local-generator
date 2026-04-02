# Attractor Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-sustaining kiosk window that shuffles and crossfades all generated media while continuously generating new prompts and queueing new video jobs, growing its pool indefinitely.

**Architecture:** A new `attractor.py` module holds `AttractorWindow` — a standalone `Gtk.Window` with no imports from `main_window.py`, communicating entirely through constructor callbacks. An A/B `Gtk.Stack` with CROSSFADE handles smooth media transitions. A daemon thread drives the generation loop with back-pressure. `main_window.py` gets a gallery toolbar launch button and notifies the window when new generations complete.

**Tech Stack:** Python 3, GTK4/PyGObject (`Gtk.Stack`, `Gtk.Video`, `Gtk.Picture`, `Gtk.Overlay`), `threading.Thread` + `threading.Event`, `GLib.idle_add`, `statistics.mean`, `prompt_client`.

---

## File Map

| File | Change |
|---|---|
| `attractor.py` | **New** — `AttractorWindow`: A/B player, sidebar, generation loop |
| `tests/test_attractor.py` | **New** — unit tests for pool logic (no GTK) |
| `main_window.py` | Add gallery toolbar, `_attractor_win`, `_on_open_attractor()`, notify on `_on_finished` |

---

## Task 1: Pool logic unit tests + `AttractorPool`

**Files:**
- Create: `attractor.py` (pool class only)
- Create: `tests/test_attractor.py`

The pool is the only pure-logic piece of `attractor.py` that can be tested without GTK. Extract it as `AttractorPool` — a plain Python class.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_attractor.py`:

```python
"""Unit tests for AttractorPool — no GTK required."""
import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent))

from attractor import AttractorPool

def _rec(media_type="video", duration_s=5.0):
    r = MagicMock()
    r.media_type = media_type
    r.duration_s = duration_s
    return r

def test_pool_order_covers_all_records():
    recs = [_rec() for _ in range(5)]
    pool = AttractorPool(recs)
    visited = set()
    for _ in range(5):
        idx = pool.advance()
        visited.add(idx)
    assert visited == {0, 1, 2, 3, 4}

def test_pool_reshuffles_after_full_cycle():
    recs = [_rec() for _ in range(3)]
    pool = AttractorPool(recs)
    first_cycle = [pool.advance() for _ in range(3)]
    second_cycle = [pool.advance() for _ in range(3)]
    assert sorted(first_cycle) == [0, 1, 2]
    assert sorted(second_cycle) == [0, 1, 2]

def test_pool_no_immediate_repeat_across_cycle():
    recs = [_rec() for _ in range(4)]
    pool = AttractorPool(recs)
    last_of_first = None
    for _ in range(4):
        last_of_first = pool.advance()
    first_of_second = pool.advance()
    assert first_of_second != last_of_first

def test_pool_add_record_appears_later_in_cycle():
    recs = [_rec() for _ in range(4)]
    pool = AttractorPool(recs)
    # advance once so _pool_pos = 1
    pool.advance()
    new_rec = _rec()
    pool.add_record(new_rec)
    # The new record's index (4) must appear at position >= current pos
    remaining = [pool.advance() for _ in range(4)]
    assert 4 in remaining

def test_avg_image_duration_uses_video_durations():
    recs = [_rec("video", 6.0), _rec("video", 10.0), _rec("image", 0.0)]
    pool = AttractorPool(recs)
    assert pool.avg_image_duration == 8.0

def test_avg_image_duration_defaults_when_no_videos():
    recs = [_rec("image", 0.0), _rec("image", 0.0)]
    pool = AttractorPool(recs)
    assert pool.avg_image_duration == 8.0

def test_current_record_returns_correct_record():
    recs = [_rec() for _ in range(3)]
    pool = AttractorPool(recs)
    idx = pool.advance()
    assert pool.current_record() is recs[idx]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd ~/code/tt-local-generator
python3 -m pytest tests/test_attractor.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'attractor'`

- [ ] **Step 3: Implement `AttractorPool` in `attractor.py`**

Create `attractor.py`:

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
"""
Attractor Mode — self-sustaining kiosk that cycles generated media and
continuously queues new generations.

Classes:
    AttractorPool  — pure pool/shuffle logic (no GTK, testable)
    AttractorWindow — GTK4 kiosk window
"""
from __future__ import annotations

import random
import statistics
import threading
from typing import Callable

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

import prompt_client  # noqa: E402

# ---------------------------------------------------------------------------
# Pool logic — no GTK, fully unit-testable
# ---------------------------------------------------------------------------

class AttractorPool:
    """
    Manages the shuffled playback order for a growing list of media records.

    Records are played in a shuffled order. When the cycle is exhausted the
    pool reshuffles, but the first item of the new cycle is never the same as
    the last item of the previous cycle.  New records added mid-cycle are
    inserted at a random position *after* the current playback position so
    they appear later in the current cycle rather than immediately next.
    """

    def __init__(self, records: list) -> None:
        self._records: list = list(records)
        self._order: list[int] = []
        self._pos: int = 0
        self._last_idx: int | None = None
        self._shuffle_fresh()
        self._recalc_duration()

    # ── public ────────────────────────────────────────────────────────────

    def advance(self) -> int:
        """
        Move to the next item and return its index into self._records.
        Reshuffles automatically at end of cycle.
        """
        if self._pos >= len(self._order):
            self._shuffle_fresh()
        idx = self._order[self._pos]
        self._last_idx = idx
        self._pos += 1
        return idx

    def current_record(self):
        """Return the record most recently returned by advance()."""
        return self._records[self._last_idx]

    def add_record(self, record) -> None:
        """
        Append a new record and insert its index at a random position after
        the current playback position in _order.
        """
        new_idx = len(self._records)
        self._records.append(record)
        # Insert anywhere from current pos to end of order
        insert_at = random.randint(self._pos, len(self._order))
        self._order.insert(insert_at, new_idx)
        self._recalc_duration()

    @property
    def avg_image_duration(self) -> float:
        """Mean duration of video records, or 8.0 s if none exist."""
        return self._avg_dur

    @property
    def size(self) -> int:
        return len(self._records)

    # ── private ───────────────────────────────────────────────────────────

    def _shuffle_fresh(self) -> None:
        order = list(range(len(self._records)))
        random.shuffle(order)
        # Avoid placing last-played item first in new cycle
        if self._last_idx is not None and order and order[0] == self._last_idx:
            if len(order) > 1:
                order[0], order[1] = order[1], order[0]
        self._order = order
        self._pos = 0

    def _recalc_duration(self) -> None:
        durations = [
            r.duration_s for r in self._records
            if r.media_type == "video" and r.duration_s > 0
        ]
        self._avg_dur = statistics.mean(durations) if durations else 8.0
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python3 -m pytest tests/test_attractor.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add attractor.py tests/test_attractor.py
git commit -m "feat: add AttractorPool with shuffle/reshuffle/add_record logic"
```

---

## Task 2: `AttractorWindow` — skeleton + CSS

**Files:**
- Modify: `attractor.py` — add `AttractorWindow` class and CSS constant

- [ ] **Step 1: Add CSS constant and `AttractorWindow.__init__` to `attractor.py`**

Append to `attractor.py` after `AttractorPool`:

```python
# ---------------------------------------------------------------------------
# CSS — registered by AttractorWindow on first instantiation
# ---------------------------------------------------------------------------

_CSS = b"""
/* Attractor sidebar */
.attractor-sidebar {
    background-color: @tt_bg_darkest;
    border-right: 1px solid @tt_border;
    padding: 10px 8px;
}
.attractor-header {
    color: @tt_accent;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}
.attractor-stat-lbl {
    color: @tt_text_muted;
    font-size: 10px;
}
.attractor-status-lbl {
    color: @tt_accent_light;
    font-size: 10px;
    font-style: italic;
}
.attractor-prompt-lbl {
    color: @tt_text_muted;
    font-size: 10px;
    font-style: italic;
}
.attractor-stop-btn {
    background-color: #2D1A1A;
    color: @tt_error;
    border: 1px solid @tt_error;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 11px;
}
.attractor-stop-btn:hover {
    background-color: @tt_border;
}
/* HUD overlay strip */
.attractor-hud {
    background: linear-gradient(transparent, rgba(0,0,0,0.55));
    padding: 20px 12px 8px;
}
.attractor-hud-lbl {
    color: rgba(232,240,242,0.55);
    font-size: 10px;
    font-style: italic;
}
"""

# ---------------------------------------------------------------------------
# AttractorWindow
# ---------------------------------------------------------------------------

class AttractorWindow(Gtk.Window):
    """
    Kiosk window: narrow sidebar with live status + A/B crossfading media player.

    All communication with MainWindow is through constructor callbacks — this
    class has no imports from main_window.py.
    """

    def __init__(
        self,
        records: list,                        # initial pool from HistoryStore.all_records()
        system_prompt: str,                   # contents of prompts/prompt_generator.md
        model_source: str,                    # "video" | "image" | "animate"
        on_enqueue: Callable,                 # MainWindow._on_enqueue compatible signature
        get_queue_depth: Callable[[], int],   # returns len(self._queue) in MainWindow
    ) -> None:
        super().__init__(title="Attractor Mode")
        self._system_prompt = system_prompt
        self._model_source = model_source
        self._on_enqueue = on_enqueue
        self._get_queue_depth = get_queue_depth
        self._pool = AttractorPool(records)
        self._gen_stop = threading.Event()
        self._paused = False
        self._pending_advance_source: int | None = None  # GLib source id

        # Load CSS (uses @define-color variables already loaded by main_window.py)
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._build()
        self.maximize()

        # Keyboard shortcuts
        ctrl = Gtk.EventControllerKey()
        ctrl.connect("key-pressed", self._on_key)
        self.add_controller(ctrl)

        self.connect("destroy", self._on_destroy)

    def _on_key(self, _ctrl, keyval, _keycode, _state) -> bool:
        name = Gtk.accelerator_name(keyval, 0)
        if name == "Escape":
            self.close()
            return True
        if name == "F11" or name == "f":
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.fullscreen()
            return True
        if name == "space":
            self._toggle_pause()
            return True
        return False

    def _on_destroy(self, _win) -> None:
        self._gen_stop.set()
        if self._pending_advance_source is not None:
            GLib.source_remove(self._pending_advance_source)
            self._pending_advance_source = None

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            stream = self._get_current_video_stream()
            if stream:
                stream.pause()
        else:
            stream = self._get_current_video_stream()
            if stream:
                stream.play()
```

- [ ] **Step 2: Add `_build()` method**

```python
    def _build(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(outer)

        # ── Sidebar ───────────────────────────────────────────────────────
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar.add_css_class("attractor-sidebar")
        sidebar.set_size_request(148, -1)

        hdr = Gtk.Label(label="✦ ATTRACTOR MODE")
        hdr.add_css_class("attractor-header")
        hdr.set_xalign(0)
        sidebar.append(hdr)

        sidebar.append(_hdivider())

        self._status_lbl = Gtk.Label(label="⬤  running")
        self._status_lbl.add_css_class("attractor-stat-lbl")
        self._status_lbl.set_xalign(0)
        sidebar.append(self._status_lbl)

        self._queue_lbl = Gtk.Label(label="⏳  queue: —")
        self._queue_lbl.add_css_class("attractor-stat-lbl")
        self._queue_lbl.set_xalign(0)
        sidebar.append(self._queue_lbl)

        self._pool_lbl = Gtk.Label(label=f"🎬  pool: {self._pool.size}")
        self._pool_lbl.add_css_class("attractor-stat-lbl")
        self._pool_lbl.set_xalign(0)
        sidebar.append(self._pool_lbl)

        sidebar.append(_hdivider())

        self._gen_status_lbl = Gtk.Label(label="Starting…")
        self._gen_status_lbl.add_css_class("attractor-status-lbl")
        self._gen_status_lbl.set_xalign(0)
        self._gen_status_lbl.set_wrap(True)
        sidebar.append(self._gen_status_lbl)

        self._prompt_lbl = Gtk.Label(label="")
        self._prompt_lbl.add_css_class("attractor-prompt-lbl")
        self._prompt_lbl.set_xalign(0)
        self._prompt_lbl.set_wrap(True)
        self._prompt_lbl.set_lines(5)
        self._prompt_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        sidebar.append(self._prompt_lbl)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)

        stop_btn = Gtk.Button(label="■  Stop")
        stop_btn.add_css_class("attractor-stop-btn")
        stop_btn.connect("clicked", lambda _: self.close())
        sidebar.append(stop_btn)

        outer.append(sidebar)

        # ── Media player ──────────────────────────────────────────────────
        player_overlay = Gtk.Overlay()
        player_overlay.set_hexpand(True)
        player_overlay.set_vexpand(True)

        # A/B Stack with crossfade
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(500)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        self._slot_a = self._make_slot()
        self._slot_b = self._make_slot()
        self._stack.add_named(self._slot_a, "a")
        self._stack.add_named(self._slot_b, "b")
        self._stack.set_visible_child_name("a")
        self._active_slot_name = "a"

        player_overlay.set_child(self._stack)

        # HUD strip overlaid at the bottom
        hud = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hud.add_css_class("attractor-hud")
        hud.set_valign(Gtk.Align.END)
        hud.set_hexpand(True)

        self._hud_prompt_lbl = Gtk.Label(label="")
        self._hud_prompt_lbl.add_css_class("attractor-hud-lbl")
        self._hud_prompt_lbl.set_hexpand(True)
        self._hud_prompt_lbl.set_xalign(0)
        self._hud_prompt_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        hud.append(self._hud_prompt_lbl)

        self._hud_pool_lbl = Gtk.Label(label="")
        self._hud_pool_lbl.add_css_class("attractor-hud-lbl")
        self._hud_pool_lbl.set_xalign(1)
        hud.append(self._hud_pool_lbl)

        player_overlay.add_overlay(hud)
        outer.append(player_overlay)

    def _make_slot(self) -> Gtk.Box:
        """A slot holds one Gtk.Video and one Gtk.Picture (only one visible at a time)."""
        box = Gtk.Box()
        box.set_hexpand(True)
        box.set_vexpand(True)

        vid = Gtk.Video()
        vid.set_hexpand(True)
        vid.set_vexpand(True)
        vid.set_autoplay(True)
        box._video = vid
        box.append(vid)

        pic = Gtk.Picture()
        pic.set_hexpand(True)
        pic.set_vexpand(True)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        pic.set_visible(False)
        box._picture = pic
        box.append(pic)

        return box


def _hdivider() -> Gtk.Separator:
    """Horizontal divider for the sidebar."""
    return Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
```

- [ ] **Step 3: Smoke-test window opens**

```bash
cd ~/code/tt-local-generator
/usr/bin/python3 - <<'EOF'
import gi; gi.require_version("Gtk","4.0")
from gi.repository import Gtk, GLib
from history_store import HistoryStore
from attractor import AttractorWindow

app = Gtk.Application(application_id="test.attractor")
def on_activate(app):
    store = HistoryStore()
    store.load()
    recs = store.all_records()
    win = AttractorWindow(recs, "", "video", lambda **kw: None, lambda: 0)
    win.set_application(app)
    win.present()
    GLib.timeout_add(2000, lambda: app.quit())
app.connect("activate", on_activate)
app.run([])
print("OK")
EOF
```

Expected: window opens briefly, closes, prints `OK`. No traceback.

- [ ] **Step 4: Commit**

```bash
git add attractor.py
git commit -m "feat: AttractorWindow skeleton with sidebar, A/B stack, and HUD"
```

---

## Task 3: Playback — load and advance media

**Files:**
- Modify: `attractor.py` — add `start()`, `_advance()`, `_load_slot()`, `_schedule_advance()`

- [ ] **Step 1: Add `start()` and all playback methods to `AttractorWindow`**

```python
    def start(self) -> None:
        """
        Begin playback and the generation loop.
        Call after the window is presented so the display is available.
        """
        if self._pool.size == 0:
            self._gen_status_lbl.set_label("No media — generating first…")
        else:
            self._advance()
        threading.Thread(
            target=self._generation_loop, daemon=True
        ).start()

    def _advance(self) -> None:
        """Load the next media item into the inactive slot and crossfade to it."""
        if self._paused:
            return
        idx = self._pool.advance()
        record = self._pool.current_record()

        # Pick inactive slot
        next_name = "b" if self._active_slot_name == "a" else "a"
        next_slot = self._slot_b if next_name == "b" else self._slot_a

        self._load_slot(next_slot, record)
        self._stack.set_visible_child_name(next_name)
        self._active_slot_name = next_name

        # Update HUD
        prompt_text = (getattr(record, "prompt", "") or "")[:100]
        self._hud_prompt_lbl.set_label(prompt_text)
        self._hud_pool_lbl.set_label(f"pool: {self._pool.size}")

        self._schedule_advance(record)

    def _load_slot(self, slot: Gtk.Box, record) -> None:
        """Load a GenerationRecord into a slot widget."""
        if record.media_type == "image":
            slot._video.set_visible(False)
            path = getattr(record, "image_path", None) or getattr(record, "thumbnail_path", None)
            if path:
                slot._picture.set_filename(path)
            slot._picture.set_visible(True)
        else:
            slot._picture.set_visible(False)
            slot._video.set_loop(True)
            path = getattr(record, "video_path", None)
            if path:
                slot._video.set_filename(path)
            slot._video.set_visible(True)

    def _schedule_advance(self, record) -> None:
        """Schedule the next _advance() call based on media type and duration."""
        if self._pending_advance_source is not None:
            GLib.source_remove(self._pending_advance_source)
            self._pending_advance_source = None

        if getattr(record, "media_type", "video") == "image":
            ms = int(self._pool.avg_image_duration * 1000)
            self._pending_advance_source = GLib.timeout_add(ms, self._on_advance_timer)
        else:
            stream = self._get_current_video_stream()
            if stream:
                stream.connect("notify::ended", self._on_video_ended)
            else:
                # Retry once stream is ready
                self._pending_advance_source = GLib.timeout_add(
                    500, self._retry_connect_stream
                )

    def _on_advance_timer(self) -> bool:
        self._pending_advance_source = None
        self._advance()
        return False

    def _on_video_ended(self, stream, _param) -> None:
        if stream.get_ended():
            self._advance()

    def _retry_connect_stream(self) -> bool:
        self._pending_advance_source = None
        stream = self._get_current_video_stream()
        if stream:
            stream.connect("notify::ended", self._on_video_ended)
        else:
            self._pending_advance_source = GLib.timeout_add(
                500, self._retry_connect_stream
            )
        return False

    def _get_current_video_stream(self):
        """Return the Gtk.MediaStream for the currently active video slot, or None."""
        slot = self._slot_b if self._active_slot_name == "b" else self._slot_a
        vid = slot._video
        if not vid.get_visible():
            return None
        return vid.get_media_stream()
```

- [ ] **Step 2: Smoke-test playback advances**

```bash
cd ~/code/tt-local-generator
/usr/bin/python3 - <<'EOF'
import gi; gi.require_version("Gtk","4.0")
from gi.repository import Gtk, GLib
from history_store import HistoryStore
from attractor import AttractorWindow

app = Gtk.Application(application_id="test.attractor2")
def on_activate(app):
    store = HistoryStore()
    store.load()
    recs = store.all_records()[:6]
    win = AttractorWindow(recs, "", "video", lambda **kw: None, lambda: 0)
    win.set_application(app)
    win.present()
    GLib.idle_add(win.start)
    GLib.timeout_add(5000, lambda: app.quit())
app.connect("activate", on_activate)
app.run([])
print("OK")
EOF
```

Expected: window opens, shows media, no traceback, prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add attractor.py
git commit -m "feat: AttractorWindow playback — load slots and advance with crossfade"
```

---

## Task 4: Generation loop + `add_record`

**Files:**
- Modify: `attractor.py` — add `_generation_loop()`, `_enqueue_generation()`, `add_record()`, sidebar update helpers

- [ ] **Step 1: Add generation loop and sidebar helpers to `AttractorWindow`**

```python
    # ── Generation loop ───────────────────────────────────────────────────

    def _generation_loop(self) -> None:
        """
        Daemon thread.  Continuously generates prompts and enqueues jobs.
        Back-pressure: if queue depth >= 2, waits 30 s before retrying.
        Stops when self._gen_stop is set (window closed).
        """
        while not self._gen_stop.wait(0.0):
            depth = self._get_queue_depth()
            GLib.idle_add(self._queue_lbl.set_label, f"⏳  queue: {depth}")

            if depth >= 2:
                GLib.idle_add(self._set_gen_status, "⏸  waiting (queue full)…")
                if self._gen_stop.wait(30.0):
                    break
                continue

            try:
                GLib.idle_add(self._set_gen_status, "✦  generating prompt…")
                prompt = prompt_client.generate_prompt(
                    source=self._model_source,
                    seed_text="",
                    system_prompt=self._system_prompt,
                )
                GLib.idle_add(self._prompt_lbl.set_label, prompt)
                GLib.idle_add(self._set_gen_status, "⏳  queued…")
                GLib.idle_add(self._enqueue_generation, prompt)
            except Exception as exc:
                GLib.idle_add(self._set_gen_status, f"⚠  {exc}")
                if self._gen_stop.wait(15.0):
                    break
                continue

            self._gen_stop.wait(5.0)

    def _enqueue_generation(self, prompt: str) -> None:
        """Called on main thread — enqueue a new generation job."""
        self._on_enqueue(
            prompt=prompt,
            negative_prompt="",
            steps=30,
            seed=-1,
            seed_image_path="",
            model_source=self._model_source,
            guidance_scale=5.0,
            ref_video_path="",
            ref_char_path="",
            animate_mode="animation",
            model_id="",
        )

    def _set_gen_status(self, text: str) -> None:
        self._gen_status_lbl.set_label(text)

    # ── New record from MainWindow ─────────────────────────────────────────

    def add_record(self, record) -> None:
        """
        Called via GLib.idle_add from MainWindow._on_finished when a new
        generation completes.  Adds the record to the live pool.
        """
        self._pool.add_record(record)
        self._pool_lbl.set_label(f"🎬  pool: {self._pool.size}")
        self._hud_pool_lbl.set_label(f"pool: {self._pool.size}")
        # If we had no media at start, begin playback now
        if self._pool.size == 1:
            self._advance()
```

- [ ] **Step 2: Smoke-test generation loop (mock enqueue)**

```bash
cd ~/code/tt-local-generator
/usr/bin/python3 - <<'EOF'
import gi; gi.require_version("Gtk","4.0")
from gi.repository import Gtk, GLib
from history_store import HistoryStore
from attractor import AttractorWindow

enqueue_calls = []
def mock_enqueue(**kw):
    enqueue_calls.append(kw["prompt"])
    print(f"[enqueue] {kw['prompt'][:60]}")

app = Gtk.Application(application_id="test.attractor3")
def on_activate(app):
    store = HistoryStore()
    store.load()
    recs = store.all_records()[:3]
    win = AttractorWindow(
        recs, "", "video",
        on_enqueue=mock_enqueue,
        get_queue_depth=lambda: len(enqueue_calls) % 3,
    )
    win.set_application(app)
    win.present()
    GLib.idle_add(win.start)
    GLib.timeout_add(12000, lambda: app.quit())
app.connect("activate", on_activate)
app.run([])
print(f"Total enqueued: {len(enqueue_calls)}")
EOF
```

Expected: sidebar shows "generating prompt…" then "queued…", at least 1 `[enqueue]` line printed (or ⚠ error if prompt server not running — both are correct).

- [ ] **Step 3: Commit**

```bash
git add attractor.py
git commit -m "feat: AttractorWindow generation loop with back-pressure and add_record"
```

---

## Task 5: MainWindow — toolbar button + wiring

**Files:**
- Modify: `main_window.py` — gallery toolbar, `_attractor_win`, `_on_open_attractor()`, import, `_on_finished` notification

- [ ] **Step 1: Add `import attractor` to imports in `main_window.py`**

Find the imports block (around line 36–40):
```python
import prompt_client
```

Add immediately before it:
```python
import attractor
```

- [ ] **Step 2: Add `.attractor-launch-btn` CSS to `_CSS` in `main_window.py`**

Find the last CSS block before the closing `"""` in `_CSS`. Add after it:

```css

/* Attractor launch button */
.attractor-launch-btn {
    background-color: @tt_bg_darkest;
    color: @tt_accent_light;
    border: 1px solid @tt_border;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
}
.attractor-launch-btn:hover {
    background-color: @tt_bg_dark;
    border-color: @tt_accent;
    color: @tt_text;
}
.attractor-launch-btn:disabled {
    color: @tt_text_muted;
    border-color: @tt_bg_dark;
}
```

- [ ] **Step 3: Add `_attractor_win` to `MainWindow.__init__`**

Find the line:
```python
        self._log_tail_stop: "threading.Event | None" = None  # set to stop server log tail
```

Add after it:
```python
        self._attractor_win: "attractor.AttractorWindow | None" = None
```

- [ ] **Step 4: Add the gallery toolbar with the Attractor button in `_build_ui()`**

Find where `gallery_wrap` is created in `_build_ui()`:
```python
        gallery_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
```

Replace with:
```python
        gallery_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Gallery toolbar
        gallery_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        gallery_toolbar.set_margin_start(6)
        gallery_toolbar.set_margin_end(6)
        gallery_toolbar.set_margin_top(4)
        gallery_toolbar.set_margin_bottom(4)
        _tb_spacer = Gtk.Box()
        _tb_spacer.set_hexpand(True)
        gallery_toolbar.append(_tb_spacer)
        self._attractor_btn = Gtk.Button(label="✦ Attractor")
        self._attractor_btn.add_css_class("attractor-launch-btn")
        self._attractor_btn.set_tooltip_text(
            "Open Attractor Mode — plays all media in a kiosk loop\n"
            "and continuously generates new content."
        )
        self._attractor_btn.set_sensitive(False)
        self._attractor_btn.connect("clicked", self._on_open_attractor)
        gallery_toolbar.append(self._attractor_btn)
        gallery_wrap.append(gallery_toolbar)
```

- [ ] **Step 5: Add `_on_open_attractor()` and `_update_attractor_btn()` to `MainWindow`**

Add these two methods (near `_on_start_prompt_gen`):

```python
    def _on_open_attractor(self, _btn=None) -> None:
        """Open (or raise) the Attractor Mode kiosk window."""
        if self._attractor_win is not None:
            self._attractor_win.present()
            return

        records = self._store.all_records()
        win = attractor.AttractorWindow(
            records=records,
            system_prompt=self._prompt_gen_system_prompt,
            model_source=self._controls.get_model_source(),
            on_enqueue=self._on_enqueue,
            get_queue_depth=lambda: len(self._queue),
        )
        win.set_transient_for(self)
        win.connect("destroy", self._on_attractor_closed)
        self._attractor_win = win
        win.present()
        GLib.idle_add(win.start)

    def _on_attractor_closed(self, _win) -> None:
        self._attractor_win = None

    def _update_attractor_btn(self) -> None:
        """Enable/disable the Attractor button based on whether any media exists."""
        has_media = len(self._store.all_records()) > 0
        self._attractor_btn.set_sensitive(has_media)
```

- [ ] **Step 6: Call `_update_attractor_btn()` from `_load_history` and `_on_finished`**

In `_load_history`, after the final gallery load call, add:
```python
        self._update_attractor_btn()
```

In `_on_finished`, after `self._start_next_queued()`, add:
```python
        if self._attractor_win is not None:
            GLib.idle_add(self._attractor_win.add_record, record)
        self._update_attractor_btn()
```

- [ ] **Step 7: Add `get_model_source()` to `ControlPanel` if not present**

Check whether `ControlPanel` already has a `get_model_source()` method. If not, add it:

```python
    def get_model_source(self) -> str:
        """Return the currently selected generation source: 'video', 'image', or 'animate'."""
        return self._model_source
```

- [ ] **Step 8: Full smoke-test**

```bash
/usr/bin/python3 main.py &
```

1. App opens — `✦ Attractor` button in gallery toolbar (disabled if no media)
2. With media present: button enabled; click it → kiosk window opens maximized
3. Sidebar shows pool count, "Starting…" / "generating prompt…" status
4. Media cycles with crossfade
5. Press `Esc` → window closes, main app fully usable
6. Click `✦ Attractor` again → new window opens

```bash
kill %1
```

- [ ] **Step 9: Commit**

```bash
git add main_window.py
git commit -m "feat: wire AttractorWindow into MainWindow — toolbar button, launch, notify on completion"
```

---

## Task 6: Full test suite + end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run all tests**

```bash
cd ~/code/tt-local-generator
python3 -m pytest tests/ -v
```

Expected: all tests pass including `tests/test_attractor.py`.

- [ ] **Step 2: End-to-end checklist**

```bash
/usr/bin/python3 main.py
```

- [ ] App opens; `✦ Attractor` button in gallery toolbar
- [ ] Button disabled when gallery empty; enabled when records exist
- [ ] Attractor window: media cycles with crossfade
- [ ] Sidebar shows live queue depth, pool size, generation status and prompt text
- [ ] Back-pressure: sidebar shows "waiting (queue full)…" when queue ≥ 2
- [ ] `■ Stop` closes window; generation loop stops
- [ ] `Esc` closes window; `F` toggles fullscreen; `Space` pauses playback
- [ ] Completing a generation in main app → pool count increments in attractor
- [ ] Closing attractor → `_attractor_win` cleared → re-opening creates fresh window
- [ ] All existing generate/queue/server/gallery flows unaffected
