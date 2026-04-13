# Animate Gallery Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the gallery a first-class input source for Animate by adding slide-up card action buttons, replacing the Browse file pickers with visual thumbnail InputWidgets backed by a three-tab popover picker (Bundled / Gallery / Disk), and adding an inline mode description bar to the Animation/Replacement toggle.

**Architecture:** New components live in `app/animate_picker.py` (keeping `main_window.py` from growing further). `BundledClipScanner` reads `app/assets/motion_clips/` at runtime. `InputWidget` is a `Gtk.Button` subclass that displays a thumbnail + name and opens `PickerPopover` on click. `PickerPopover` is a `Gtk.Popover` with a `Gtk.Stack` for three tabs. Gallery card hover action bars use `Gtk.Revealer(SLIDE_UP)` overlays. The mode description bar uses `Gtk.Revealer(SLIDE_DOWN)` below the toggle. `MainWindow` wires card action callbacks through `GalleryWidget` → `ControlPanel.set_motion_input` / `set_char_input`.

**Tech Stack:** GTK4/Python, `gi.repository.Gtk/GLib/GdkPixbuf/Pango`, ffmpeg (thumbnail extraction), existing `HistoryStore`/`GenerationRecord`/`AppSettings` patterns.

---

## File Structure

| File | Role |
|------|------|
| `app/animate_picker.py` | New — `extract_thumbnail`, `BundledClipScanner`, `InputWidget`, `PickerPopover` |
| `app/main_window.py` | Modify — new CSS, `GenerationCard` action bar, `GalleryWidget` callbacks, `ControlPanel` input replacements + mode bar |
| `app/app_settings.py` | Modify — add `motion_clips_dir` default |
| `tests/test_animate_picker.py` | New — unit tests for `BundledClipScanner` and `InputWidget.set_value` |

---

## Task 1: Add `motion_clips_dir` to AppSettings

**Files:**
- Modify: `app/app_settings.py:33-57`
- Test: `tests/test_app_settings.py`

- [ ] **Step 1: Verify existing test passes**

```bash
cd /home/ttuser/code/tt-local-generator
python -m pytest tests/test_app_settings.py -v
```
Expected: all pass.

- [ ] **Step 2: Add the new key to DEFAULTS**

In `app/app_settings.py`, add `"motion_clips_dir": ""` to the `DEFAULTS` dict after the `"dismissed_job_ids"` entry (line ~56):

```python
    # Animate picker — user-chosen disk folder
    "motion_clips_dir": "",         # empty = Disk tab shows only Browse tile
```

- [ ] **Step 3: Add test for the new key**

Add to `tests/test_app_settings.py` (append before the last blank line):

```python
def test_motion_clips_dir_default_is_empty_string(tmp_path, monkeypatch):
    """motion_clips_dir defaults to '' when not set."""
    monkeypatch.setattr("app_settings.SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr("app_settings.STORAGE_DIR", tmp_path)
    from importlib import reload
    import app_settings as _mod
    reload(_mod)
    s = _mod.AppSettings()
    assert s.get("motion_clips_dir") == ""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_app_settings.py -v
```
Expected: all pass including the new test.

- [ ] **Step 5: Commit**

```bash
git add app/app_settings.py tests/test_app_settings.py
git commit -m "feat: add motion_clips_dir setting for animate popover disk tab"
```

---

## Task 2: Add new CSS classes for picker and action bar

**Files:**
- Modify: `app/main_window.py:53-550` (the `_CSS` bytes literal)

- [ ] **Step 1: Locate the CSS insertion point**

Open `app/main_window.py`. The `_CSS` literal runs from line 53 to approximately line 550. Find the block that ends with the animate-inputs styles (search for `.animate-inputs-title`). We will append new rules after the last existing rule.

- [ ] **Step 2: Add the CSS block**

Append the following CSS inside the `_CSS` bytes literal, immediately before the closing `"""` (which is a `b"""` string, so use the same backslash encoding). Insert after the last existing style block:

```css
/* -- Animate InputWidget ---------------------------------------------------- */
.input-widget {
    background-color: @tt_bg_dark;
    border: 1px solid @tt_border;
    border-radius: 4px;
    padding: 0;
}
.input-widget:hover {
    border-color: @tt_accent_light;
}
.input-widget-filled-motion {
    border-color: @tt_pink;
}
.input-widget-filled-char {
    border-color: @tt_accent;
}
.input-widget-type {
    color: @tt_text_muted;
    font-size: 7px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
.input-widget-name {
    font-size: 8px;
    color: @tt_text;
}
.input-widget-placeholder {
    color: @tt_text_muted;
    font-size: 18px;
}
.input-widget-thumb {
    background-color: @tt_bg_darkest;
    border-radius: 2px;
}
.input-widget-caret {
    font-size: 8px;
    color: @tt_text_muted;
}

/* -- Gallery card hover action bar ------------------------------------------ */
.hover-action-bar {
    background: linear-gradient(to top, rgba(10,30,40,0.92), transparent);
    padding: 6px 4px 4px 4px;
}
.hover-action-btn {
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: bold;
    border: 1px solid @tt_border;
    background-color: rgba(15,42,53,0.85);
    min-height: 0;
}
.hover-action-btn label {
    padding: 0;
    margin: 0;
}
.hover-action-btn-animate {
    color: @tt_accent;
    border-color: @tt_accent;
}
.hover-action-btn-animate:hover {
    background-color: @tt_accent;
    color: @tt_bg_darkest;
}
.hover-action-btn-motion {
    color: @tt_pink;
    border-color: @tt_pink;
}
.hover-action-btn-motion:hover {
    background-color: @tt_pink;
    color: @tt_bg_darkest;
}

/* -- Mode description bar --------------------------------------------------- */
.mode-desc-bar {
    background-color: @tt_bg_dark;
    border: 1px solid @tt_border;
    border-top: none;
    border-radius: 0 0 4px 4px;
    padding: 5px 8px;
}
.mode-desc-bar-anim {
    border-color: @tt_accent;
}
.mode-desc-bar-repl {
    border-color: @tt_pink;
}
.mode-desc-bar-icon {
    font-size: 14px;
}
.mode-desc-bar-text {
    font-size: 9px;
    color: @tt_text;
}
.mode-desc-bar-impact-anim {
    font-size: 8px;
    color: @tt_accent;
}
.mode-desc-bar-impact-repl {
    font-size: 8px;
    color: @tt_pink;
}

/* -- Picker popover --------------------------------------------------------- */
popover.picker-popover > contents {
    background-color: @tt_bg_darkest;
    border: 1px solid @tt_accent;
    border-radius: 6px;
    padding: 0;
}
.picker-title {
    font-size: 10px;
    font-weight: bold;
    color: @tt_accent;
}
.picker-tab-btn {
    background-color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    color: @tt_text_muted;
    font-size: 9px;
    padding: 3px 8px;
    min-height: 0;
}
.picker-tab-btn label { padding: 0; margin: 0; }
.picker-tab-btn:hover { color: @tt_text; border-bottom-color: @tt_border; }
.picker-tab-btn-active {
    color: @tt_accent;
    border-bottom-color: @tt_accent;
    font-weight: bold;
}
.picker-tab-btn-active:hover { color: @tt_accent_light; }
.picker-thumb-cell {
    background-color: @tt_bg_dark;
    border: 1px solid @tt_border;
    border-radius: 3px;
    min-width: 60px;
    min-height: 44px;
}
.picker-thumb-cell:hover { border-color: @tt_accent_light; }
.picker-thumb-cell-selected {
    border-color: @tt_accent;
    border-width: 2px;
}
.picker-cat-chip {
    background-color: @tt_bg_dark;
    border: 1px solid @tt_border;
    border-radius: 10px;
    color: @tt_text_muted;
    font-size: 8px;
    padding: 2px 7px;
    min-height: 0;
}
.picker-cat-chip label { padding: 0; margin: 0; }
.picker-cat-chip:hover { border-color: @tt_accent; color: @tt_text; }
.picker-cat-chip-active {
    border-color: @tt_accent;
    color: @tt_accent;
}
.picker-folder-row {
    background-color: @tt_bg_dark;
    border: 1px solid @tt_border;
    border-radius: 3px;
    padding: 4px 6px;
}
.picker-empty {
    color: @tt_text_muted;
    font-size: 10px;
}
.picker-browse-tile {
    background-color: transparent;
    border: 1px dashed @tt_accent;
    border-radius: 3px;
    color: @tt_accent;
    font-size: 10px;
    min-width: 60px;
    min-height: 44px;
}
.picker-browse-tile label { padding: 0; margin: 0; }
.picker-use-btn {
    background-color: @tt_accent;
    color: @tt_bg_darkest;
    border-color: @tt_accent;
    border-radius: 3px;
    font-size: 9px;
    font-weight: bold;
    padding: 3px 8px;
    min-height: 0;
}
.picker-use-btn label { padding: 0; margin: 0; }
.picker-use-btn:disabled { background-color: @tt_border; color: @tt_text_muted; }
.picker-cancel-btn {
    background-color: @tt_bg_dark;
    border: 1px solid @tt_border;
    border-radius: 3px;
    color: @tt_text_muted;
    font-size: 9px;
    padding: 3px 8px;
    min-height: 0;
}
.picker-cancel-btn label { padding: 0; margin: 0; }
```

- [ ] **Step 3: Verify the app still loads (smoke test)**

```bash
cd /home/ttuser/code/tt-local-generator
source build/env/activate 2>/dev/null || true
python -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; from app.main_window import _CSS; p = Gtk.CssProvider(); p.load_from_data(_CSS); print('CSS OK')" 2>&1 | grep -v "Gtk-CSS-WARNING"
```
Expected: `CSS OK` (CSS warnings about unknown properties are acceptable; errors/exceptions are not).

- [ ] **Step 4: Commit**

```bash
git add app/main_window.py
git commit -m "style: add CSS classes for animate InputWidget, action bar, mode bar, picker popover"
```

---

## Task 3: Create `app/animate_picker.py` with `extract_thumbnail` and `BundledClipScanner`

**Files:**
- Create: `app/animate_picker.py`
- Create: `tests/test_animate_picker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_animate_picker.py`:

```python
"""
Unit tests for animate_picker — BundledClipScanner and extract_thumbnail.
No GTK display required for these tests.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from animate_picker import BundledClipScanner, extract_thumbnail


def test_bundled_scanner_empty_dir_returns_empty(tmp_path):
    """Scanning a non-existent directory returns {}."""
    scanner = BundledClipScanner(str(tmp_path / "nonexistent"))
    assert scanner.scan() == {}


def test_bundled_scanner_empty_clips_dir_returns_empty(tmp_path):
    """A clips dir with no subdirectories returns {}."""
    clips_dir = tmp_path / "motion_clips"
    clips_dir.mkdir()
    scanner = BundledClipScanner(str(clips_dir))
    assert scanner.scan() == {}


def test_bundled_scanner_discovers_categories_and_clips(tmp_path):
    """Scanner finds category subdirs and MP4 files within them."""
    clips_dir = tmp_path / "motion_clips"
    walk_dir = clips_dir / "walk"
    walk_dir.mkdir(parents=True)
    (walk_dir / "walk_forward.mp4").write_bytes(b"fake-mp4")
    (walk_dir / "walk_backward.mp4").write_bytes(b"fake-mp4")
    (clips_dir / "readme.txt").write_text("not a dir")  # should be ignored

    # Patch extract_thumbnail so no ffmpeg call is made
    with patch("animate_picker.extract_thumbnail", return_value=False):
        scanner = BundledClipScanner(str(clips_dir))
        result = scanner.scan()

    assert "walk" in result
    names = {clip["name"] for clip in result["walk"]}
    assert names == {"walk_forward", "walk_backward"}
    assert len(result) == 1  # only the 'walk' category


def test_bundled_scanner_skips_dirs_with_no_mp4(tmp_path):
    """A subdirectory with no MP4 files is omitted from results."""
    clips_dir = tmp_path / "motion_clips"
    empty_cat = clips_dir / "gestures"
    empty_cat.mkdir(parents=True)
    (empty_cat / "readme.txt").write_text("no clips yet")

    with patch("animate_picker.extract_thumbnail", return_value=False):
        result = BundledClipScanner(str(clips_dir)).scan()

    assert result == {}


def test_bundled_scanner_clip_dict_has_required_keys(tmp_path):
    """Each clip dict has 'name', 'mp4', and 'thumb' keys."""
    clips_dir = tmp_path / "motion_clips"
    (clips_dir / "run").mkdir(parents=True)
    mp4 = clips_dir / "run" / "run_forward.mp4"
    mp4.write_bytes(b"fake")

    with patch("animate_picker.extract_thumbnail", return_value=False):
        result = BundledClipScanner(str(clips_dir)).scan()

    clip = result["run"][0]
    assert clip["name"] == "run_forward"
    assert clip["mp4"] == str(mp4)
    assert "thumb" in clip


def test_extract_thumbnail_returns_false_on_missing_ffmpeg(tmp_path):
    """extract_thumbnail returns False when ffmpeg is not found."""
    src = str(tmp_path / "video.mp4")
    dest = str(tmp_path / "thumb.jpg")
    Path(src).write_bytes(b"fake")

    with patch("subprocess.run", side_effect=FileNotFoundError("ffmpeg not found")):
        result = extract_thumbnail(src, dest)

    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/ttuser/code/tt-local-generator
python -m pytest tests/test_animate_picker.py -v 2>&1 | head -20
```
Expected: FAIL with `ModuleNotFoundError: No module named 'animate_picker'`.

- [ ] **Step 3: Create `app/animate_picker.py`**

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
"""
animate_picker.py — Animate input widgets and popover picker for tt-local-generator.

Components:
    extract_thumbnail   — thin ffmpeg wrapper; returns True on success
    BundledClipScanner  — scans app/assets/motion_clips/ subdirectory tree
    InputWidget         — Gtk.Button subclass for motion/character inputs
    PickerPopover       — Gtk.Popover with Bundled / Gallery / Disk tabs
"""
import subprocess
from pathlib import Path
from typing import Optional


def extract_thumbnail(src_path: str, dest_path: str) -> bool:
    """
    Extract the first frame of *src_path* as a JPEG saved to *dest_path*.

    Returns True when ffmpeg succeeds and the output file exists.
    Returns False silently on any error (ffmpeg absent, timeout, corrupt input).
    """
    try:
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", src_path,
                "-vframes", "1",
                "-q:v", "2",
                "-update", "1",
                dest_path,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0 and Path(dest_path).exists()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


class BundledClipScanner:
    """
    Scans a motion_clips directory tree for bundled MP4 clips.

    Directory layout expected:
        <clips_dir>/
            <category>/
                <clip_name>.mp4
                <clip_name>.jpg   ← thumbnail, extracted on first scan if absent

    Usage:
        scanner = BundledClipScanner("app/assets/motion_clips")
        data = scanner.scan()
        # {"walk": [{"name": "walk_forward", "mp4": "...", "thumb": "..."}, ...], ...}
    """

    def __init__(self, clips_dir: str) -> None:
        self._clips_dir = Path(clips_dir)

    def scan(self) -> dict:
        """
        Return a dict mapping category name → list of clip dicts.

        Each clip dict: {"name": str, "mp4": str, "thumb": str}
        Categories are sorted alphabetically; clips within each category are
        sorted alphabetically by filename stem.
        """
        result: dict = {}
        if not self._clips_dir.is_dir():
            return result

        for cat_dir in sorted(self._clips_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            clips = []
            for mp4_path in sorted(cat_dir.glob("*.mp4")):
                thumb_path = mp4_path.with_suffix(".jpg")
                if not thumb_path.exists():
                    extract_thumbnail(str(mp4_path), str(thumb_path))
                clips.append({
                    "name": mp4_path.stem,
                    "mp4":  str(mp4_path),
                    "thumb": str(thumb_path),
                })
            if clips:
                result[cat_dir.name] = clips

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_animate_picker.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/animate_picker.py tests/test_animate_picker.py
git commit -m "feat: add animate_picker.py with extract_thumbnail and BundledClipScanner"
```

---

## Task 4: Add `InputWidget` to `animate_picker.py`

**Files:**
- Modify: `app/animate_picker.py`
- Modify: `tests/test_animate_picker.py`

`InputWidget` is a `Gtk.Button` subclass that displays a type label, 40 px thumbnail area, and a filename/caret row. Clicking opens the popover picker (wired in Task 8). `set_value(path)` updates the thumbnail and filled CSS class.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_animate_picker.py` (GTK tests require a display; skip if unavailable):

```python
# ---------- InputWidget tests (require DISPLAY) ----------

import pytest

def _gtk_available() -> bool:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        app = Gtk.Application(application_id="test.animate.picker")
        return True
    except Exception:
        return False

gtk_required = pytest.mark.skipif(
    not _gtk_available(), reason="GTK4 display not available"
)


@gtk_required
def test_input_widget_empty_on_construction():
    """An InputWidget constructed with no path has no filled CSS class."""
    from animate_picker import InputWidget
    w = InputWidget("motion", "MOTION VIDEO")
    assert not w.has_css_class("input-widget-filled-motion")
    assert not w.has_css_class("input-widget-filled-char")


@gtk_required
def test_input_widget_set_value_nonexistent_path_stays_empty():
    """set_value with a path that doesn't exist leaves the widget empty."""
    from animate_picker import InputWidget
    w = InputWidget("motion", "MOTION VIDEO")
    w.set_value("/nonexistent/path/to/clip.mp4")
    assert not w.has_css_class("input-widget-filled-motion")


@gtk_required
def test_input_widget_set_value_existing_image_adds_filled_char(tmp_path):
    """set_value with a real image file adds input-widget-filled-char class."""
    from animate_picker import InputWidget
    img = tmp_path / "char.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # minimal JPEG header
    w = InputWidget("char", "CHARACTER")
    w.set_value(str(img))
    assert w.has_css_class("input-widget-filled-char")


@gtk_required
def test_input_widget_clear_removes_filled_class(tmp_path):
    """set_value('') removes the filled CSS class."""
    from animate_picker import InputWidget
    img = tmp_path / "char.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    w = InputWidget("char", "CHARACTER")
    w.set_value(str(img))
    assert w.has_css_class("input-widget-filled-char")
    w.set_value("")
    assert not w.has_css_class("input-widget-filled-char")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_animate_picker.py::test_input_widget_empty_on_construction -v 2>&1 | tail -10
```
Expected: FAIL with `ImportError` (InputWidget not yet defined).

- [ ] **Step 3: Add `InputWidget` to `app/animate_picker.py`**

Add the following imports at the top of the file (after the existing imports):

```python
from typing import Optional
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import GdkPixbuf, Gtk, Pango
```

Then append the `InputWidget` class at the bottom of `app/animate_picker.py`:

```python
# ── InputWidget ───────────────────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}


class InputWidget(Gtk.Button):
    """
    Clickable thumbnail widget for selecting a motion video or character image.

    Layout (vertical, inside the button):
      ┌────────────────────────┐
      │ MOTION VIDEO (8 px)    │  ← type label
      │ ┌──────────────────┐   │
      │ │ thumbnail / +    │   │  ← 40 px tall thumb area
      │ └──────────────────┘   │
      │ filename.mp4       ▾   │  ← name row
      └────────────────────────┘

    CSS classes applied to the button:
      .input-widget          — always present
      .input-widget-filled-motion — when widget_type=="motion" and path is set
      .input-widget-filled-char   — when widget_type=="char" and path is set

    Call set_value(path) to update programmatically (gallery card actions do this).
    Clicking the widget opens the PickerPopover (wired by ControlPanel in Task 8).
    """

    def __init__(self, widget_type: str, label: str) -> None:
        """
        Args:
            widget_type: "motion" or "char"
            label:       Type label text, e.g. "MOTION VIDEO" or "CHARACTER"
        """
        super().__init__()
        self._widget_type: str = widget_type
        self._path: str = ""
        self.add_css_class("input-widget")
        self.set_hexpand(True)

        # Vertical content box inside the button
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(5)
        box.set_margin_end(5)
        self.set_child(box)

        # Type label — muted uppercase
        type_lbl = Gtk.Label(label=label)
        type_lbl.add_css_class("input-widget-type")
        type_lbl.set_xalign(0)
        box.append(type_lbl)

        # Thumbnail area — 40 px tall
        self._thumb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._thumb_box.add_css_class("input-widget-thumb")
        self._thumb_box.set_size_request(-1, 40)
        self._thumb_box.set_hexpand(True)
        box.append(self._thumb_box)
        self._show_placeholder()

        # Name row — filename truncated + ▾ caret
        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self._name_lbl = Gtk.Label(label="none")
        self._name_lbl.add_css_class("input-widget-name")
        self._name_lbl.add_css_class("muted")
        self._name_lbl.set_hexpand(True)
        self._name_lbl.set_ellipsize(Pango.EllipsizeMode.START)
        self._name_lbl.set_xalign(0)
        caret_lbl = Gtk.Label(label="▾")
        caret_lbl.add_css_class("input-widget-caret")
        name_row.append(self._name_lbl)
        name_row.append(caret_lbl)
        box.append(name_row)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_value(self, path: str) -> None:
        """
        Update the widget to show a thumbnail and filename for *path*.
        Pass an empty string to clear back to the placeholder state.
        """
        self._path = path
        filled_class = f"input-widget-filled-{self._widget_type}"

        # Clear existing thumb children
        self._clear_thumb()

        if path and Path(path).exists():
            thumb_path = self._resolve_thumb_path(path)
            if thumb_path and Path(thumb_path).exists():
                pic = Gtk.Picture.new_for_filename(thumb_path)
                pic.set_can_shrink(True)
                pic.set_hexpand(True)
                self._thumb_box.append(pic)
            else:
                # ffmpeg failed or unavailable — show emoji placeholder
                suffix = Path(path).suffix.lower()
                emoji = "🎬" if suffix in _VIDEO_EXTENSIONS else "🖼"
                self._show_placeholder(emoji)
            self._name_lbl.set_label(Path(path).name)
            self._name_lbl.remove_css_class("muted")
            self.add_css_class(filled_class)
        else:
            self._show_placeholder()
            self._name_lbl.set_label("none")
            self._name_lbl.add_css_class("muted")
            self.remove_css_class(filled_class)

    def get_path(self) -> str:
        """Return the currently selected path, or "" if empty."""
        return self._path

    # ── Private helpers ────────────────────────────────────────────────────────

    def _clear_thumb(self) -> None:
        child = self._thumb_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._thumb_box.remove(child)
            child = nxt

    def _show_placeholder(self, emoji: str = "＋") -> None:
        """Fill the thumb area with an emoji placeholder label."""
        self._clear_thumb()
        lbl = Gtk.Label(label=emoji)
        lbl.add_css_class("input-widget-placeholder")
        lbl.set_hexpand(True)
        lbl.set_vexpand(True)
        lbl.set_valign(Gtk.Align.CENTER)
        self._thumb_box.append(lbl)

    def _resolve_thumb_path(self, src_path: str) -> Optional[str]:
        """
        Return a path to a JPEG thumbnail for *src_path*.

        For image files: the file itself is the thumbnail.
        For video files: <same_dir>/<stem>.jpg, extracted via ffmpeg on first call.
        Returns None if thumbnail cannot be obtained.
        """
        p = Path(src_path)
        if p.suffix.lower() in _IMAGE_EXTENSIONS:
            return src_path
        # Video: cache thumbnail as <stem>.jpg next to the file
        thumb = p.with_suffix(".jpg")
        if not thumb.exists():
            ok = extract_thumbnail(src_path, str(thumb))
            if not ok:
                return None
        return str(thumb)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_animate_picker.py -v
```
Expected: all 10 tests PASS (GTK tests skipped if no display).

- [ ] **Step 5: Commit**

```bash
git add app/animate_picker.py tests/test_animate_picker.py
git commit -m "feat: add InputWidget to animate_picker"
```

---

## Task 5: Add `PickerPopover` to `animate_picker.py`

**Files:**
- Modify: `app/animate_picker.py`

`PickerPopover` is a `Gtk.Popover` anchored to an `InputWidget`. It contains a title bar, tab strip (Gtk.Stack tabs), scrollable content area, and a footer with Cancel / Use this buttons. The Character picker omits the Bundled tab. `on_select(path)` is called when the user clicks "Use this".

- [ ] **Step 1: Append `PickerPopover` to `app/animate_picker.py`**

```python
# ── PickerPopover ─────────────────────────────────────────────────────────────


class PickerPopover(Gtk.Popover):
    """
    Three-tab popover picker anchored to an InputWidget.

    Tabs:
      📦 Bundled — clips from app/assets/motion_clips/ (motion picker only)
      🎬 Gallery — records from HistoryStore
      📁 Disk    — files from a user-chosen folder (saved in AppSettings)

    Args:
        widget_type:      "motion" or "char"
        clips_dir:        path to app/assets/motion_clips/ (used for Bundled tab)
        history_records:  list of GenerationRecord from HistoryStore.all_records()
        settings:         AppSettings instance
        on_select:        callable(path: str) — called when user confirms selection

    Usage:
        popover = PickerPopover("motion", clips_dir, records, settings, on_select)
        popover.set_parent(input_widget)
        popover.popup()
    """

    def __init__(
        self,
        widget_type: str,
        clips_dir: str,
        history_records: list,
        settings,
        on_select,
    ) -> None:
        super().__init__()
        self._widget_type = widget_type
        self._clips_dir = clips_dir
        self._history_records = history_records
        self._settings = settings
        self._on_select = on_select
        self._selected_path: Optional[str] = None

        self.add_css_class("picker-popover")
        self.set_size_request(300, -1)

        # Outer vertical box — all popover content lives here
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(8)
        outer.set_margin_bottom(0)
        outer.set_margin_start(0)
        outer.set_margin_end(0)
        self.set_child(outer)

        # ── Header: title + close button ──────────────────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_margin_start(10)
        header.set_margin_end(6)
        header.set_margin_bottom(4)
        title_text = "Pick Motion Video" if widget_type == "motion" else "Pick Character Image"
        title_lbl = Gtk.Label(label=title_text)
        title_lbl.add_css_class("picker-title")
        title_lbl.set_hexpand(True)
        title_lbl.set_xalign(0)
        close_btn = Gtk.Button(label="✕")
        close_btn.add_css_class("trash-btn")  # reuse small transparent button style
        close_btn.connect("clicked", lambda _: self.popdown())
        header.append(title_lbl)
        header.append(close_btn)
        outer.append(header)

        # ── Tab strip ─────────────────────────────────────────────────────────
        tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tab_box.set_margin_start(4)
        tab_box.set_margin_end(4)
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        outer.append(tab_box)
        outer.append(sep)

        # ── Stack (one page per tab) ───────────────────────────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.NONE)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(160)
        scroll.set_max_content_height(260)
        scroll.set_child(self._stack)
        outer.append(scroll)

        # ── Build tabs ────────────────────────────────────────────────────────
        self._tab_btns: dict = {}

        if widget_type == "motion":
            self._add_tab(tab_box, "bundled", "📦 Bundled", self._build_bundled_page())
        self._add_tab(tab_box, "gallery", "🎬 Gallery", self._build_gallery_page())
        self._add_tab(tab_box, "disk", "📁 Disk", self._build_disk_page())

        # Activate the first available tab
        first_tab = "bundled" if widget_type == "motion" else "gallery"
        self._activate_tab(first_tab)

        # ── Footer: Cancel + Use this ─────────────────────────────────────────
        footer_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        outer.append(footer_sep)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        footer.set_halign(Gtk.Align.END)
        footer.set_margin_top(6)
        footer.set_margin_bottom(6)
        footer.set_margin_end(10)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("picker-cancel-btn")
        cancel_btn.connect("clicked", lambda _: self.popdown())
        self._use_btn = Gtk.Button(label="Use this")
        self._use_btn.add_css_class("picker-use-btn")
        self._use_btn.set_sensitive(False)
        self._use_btn.connect("clicked", self._on_use_clicked)
        footer.append(cancel_btn)
        footer.append(self._use_btn)
        outer.append(footer)

    # ── Tab management ─────────────────────────────────────────────────────────

    def _add_tab(self, tab_box: Gtk.Box, name: str, label: str, page: Gtk.Widget) -> None:
        btn = Gtk.ToggleButton(label=label)
        btn.add_css_class("picker-tab-btn")
        btn.connect("clicked", lambda b, n=name: self._activate_tab(n))
        tab_box.append(btn)
        self._tab_btns[name] = btn
        self._stack.add_named(page, name)

    def _activate_tab(self, name: str) -> None:
        self._stack.set_visible_child_name(name)
        for tab_name, btn in self._tab_btns.items():
            if tab_name == name:
                btn.add_css_class("picker-tab-btn-active")
                btn.set_active(True)
            else:
                btn.remove_css_class("picker-tab-btn-active")
                btn.set_active(False)
        # Clear selection when switching tabs
        self._set_selection(None)

    # ── Tab page builders ─────────────────────────────────────────────────────

    def _build_bundled_page(self) -> Gtk.Widget:
        """📦 Bundled tab — scans app/assets/motion_clips/ at open time."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_bottom(4)

        scanner = BundledClipScanner(self._clips_dir)
        data = scanner.scan()

        if not data:
            lbl = Gtk.Label(label="No bundled clips found.")
            lbl.add_css_class("picker-empty")
            box.append(lbl)
            return box

        # Category filter chips
        cat_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        cat_row.set_hexpand(True)
        # Wrap in a FlowBox so chips wrap on narrow popover
        cat_flow = Gtk.FlowBox()
        cat_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        cat_flow.set_row_spacing(4)
        cat_flow.set_column_spacing(4)

        # Thumbnail grid
        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_row_spacing(5)
        grid.set_column_spacing(5)
        grid.set_min_children_per_line(3)
        grid.set_max_children_per_line(6)

        # All clips flattened, indexed by category
        all_clips: dict = data  # category → list of clip dicts
        all_flat: list = [clip for clips in data.values() for clip in clips]

        self._bundled_cells: list = []  # track all cell widgets for selection

        def _populate_grid(clips: list) -> None:
            # Remove all children
            child = grid.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                grid.remove(child)
                child = nxt
            self._bundled_cells.clear()
            for clip in clips:
                cell = self._make_thumb_cell(clip["name"], clip["thumb"], clip["mp4"])
                self._bundled_cells.append(cell)
                grid.append(cell)

        # Build category chip buttons
        active_chip: dict = {"btn": None}

        def _on_cat_clicked(btn, cat_name: str) -> None:
            if active_chip["btn"]:
                active_chip["btn"].remove_css_class("picker-cat-chip-active")
            active_chip["btn"] = btn
            btn.add_css_class("picker-cat-chip-active")
            _populate_grid(all_clips[cat_name])
            self._set_selection(None)

        for cat_name in sorted(data.keys()):
            chip_btn = Gtk.Button(label=cat_name.capitalize())
            chip_btn.add_css_class("picker-cat-chip")
            chip_btn.connect("clicked", _on_cat_clicked, cat_name)
            cat_flow.append(chip_btn)

        box.append(cat_flow)
        _populate_grid(all_flat)
        box.append(grid)
        return box

    def _build_gallery_page(self) -> Gtk.Widget:
        """🎬 Gallery tab — reads HistoryStore records."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_bottom(4)

        if self._widget_type == "motion":
            records = [r for r in self._history_records
                       if r.media_type == "video" and r.video_exists]
            hint = "Your generated videos — newest first"
        else:
            # Character: show all records with a thumbnail (first-frame stills work)
            records = [r for r in self._history_records if r.thumbnail_exists]
            hint = "Your generated outputs — newest first"

        if not records:
            lbl = Gtk.Label(label="No generated outputs yet.")
            lbl.add_css_class("picker-empty")
            box.append(lbl)
            return box

        hint_lbl = Gtk.Label(label=hint)
        hint_lbl.add_css_class("picker-empty")
        hint_lbl.set_xalign(0)
        box.append(hint_lbl)

        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_row_spacing(5)
        grid.set_column_spacing(5)
        grid.set_min_children_per_line(3)
        grid.set_max_children_per_line(6)

        for rec in records:
            # For motion picker: path = video_path. For char picker: path = thumbnail_path.
            media_path = rec.video_path if self._widget_type == "motion" else rec.thumbnail_path
            label = rec.id[:8]
            cell = self._make_thumb_cell(label, rec.thumbnail_path, media_path)
            grid.append(cell)

        box.append(grid)
        return box

    def _build_disk_page(self) -> Gtk.Widget:
        """📁 Disk tab — user-chosen folder scanned on open."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_bottom(4)

        folder = self._settings.get("motion_clips_dir") or ""

        # Folder path row
        folder_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        folder_row.add_css_class("picker-folder-row")
        folder_icon = Gtk.Label(label="📁")
        folder_path_lbl = Gtk.Label(label=folder if folder else "No folder selected")
        folder_path_lbl.add_css_class("picker-empty")
        folder_path_lbl.set_hexpand(True)
        folder_path_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        folder_path_lbl.set_xalign(0)
        change_btn = Gtk.Button(label="Change…")
        change_btn.add_css_class("picker-cancel-btn")

        def _change_folder(_btn):
            dlg = Gtk.FileDialog()
            dlg.set_title("Select Motion Clips Folder")
            dlg.select_folder(None, None, self._on_folder_chosen)

        change_btn.connect("clicked", _change_folder)
        folder_row.append(folder_icon)
        folder_row.append(folder_path_lbl)
        folder_row.append(change_btn)
        box.append(folder_row)

        # Grid of video/image files in the folder
        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_row_spacing(5)
        grid.set_column_spacing(5)
        grid.set_min_children_per_line(3)
        grid.set_max_children_per_line(6)

        if folder and Path(folder).is_dir():
            self._populate_disk_grid(grid, folder)
        else:
            empty_lbl = Gtk.Label(label="No folder — drag clips here or click Change…")
            empty_lbl.add_css_class("picker-empty")
            empty_lbl.set_wrap(True)
            grid.append(empty_lbl)

        # Dashed "Browse…" tile for one-off file picks
        browse_tile = Gtk.Button(label="＋\nBrowse…")
        browse_tile.add_css_class("picker-browse-tile")
        browse_tile.connect("clicked", self._on_browse_file)
        grid.append(browse_tile)
        box.append(grid)
        return box

    def _populate_disk_grid(self, grid: Gtk.FlowBox, folder: str) -> None:
        """Add thumbnail cells for all video/image files in *folder*."""
        folder_path = Path(folder)
        cache_dir = Path.home() / ".cache" / "tt-video-gen" / "disk_thumbs"
        cache_dir.mkdir(parents=True, exist_ok=True)

        extensions = set(_VIDEO_EXTENSIONS) | set(_IMAGE_EXTENSIONS)
        files = sorted(
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in extensions
        )

        if not files:
            lbl = Gtk.Label(label="No files in folder — drag some in or click Browse.")
            lbl.add_css_class("picker-empty")
            lbl.set_wrap(True)
            grid.append(lbl)
            return

        for file_path in files:
            if file_path.suffix.lower() in _IMAGE_EXTENSIONS:
                thumb_path = str(file_path)
            else:
                # Cache video thumbnails in ~/.cache/tt-video-gen/disk_thumbs/
                thumb_name = file_path.stem + "_" + str(abs(hash(str(file_path))))[:8] + ".jpg"
                thumb_path_obj = cache_dir / thumb_name
                if not thumb_path_obj.exists():
                    extract_thumbnail(str(file_path), str(thumb_path_obj))
                thumb_path = str(thumb_path_obj) if thumb_path_obj.exists() else ""

            cell = self._make_thumb_cell(file_path.name[:12], thumb_path, str(file_path))
            grid.append(cell)

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _make_thumb_cell(self, label: str, thumb_path: str, media_path: str) -> Gtk.Widget:
        """Return a 60×44 thumbnail cell widget for the picker grid."""
        overlay = Gtk.Overlay()
        frame = Gtk.Frame()
        frame.add_css_class("picker-thumb-cell")
        frame.set_size_request(60, 44)
        overlay.set_child(frame)

        if thumb_path and Path(thumb_path).exists():
            pic = Gtk.Picture.new_for_filename(thumb_path)
            pic.set_can_shrink(True)
            pic.set_hexpand(True)
            pic.set_vexpand(True)
            frame.set_child(pic)
        else:
            icon = Gtk.Label(label="🎬")
            icon.set_valign(Gtk.Align.CENTER)
            icon.set_halign(Gtk.Align.CENTER)
            frame.set_child(icon)

        # Filename label overlaid at bottom
        name_lbl = Gtk.Label(label=label)
        name_lbl.add_css_class("picker-empty")
        name_lbl.set_valign(Gtk.Align.END)
        name_lbl.set_halign(Gtk.Align.FILL)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        overlay.add_overlay(name_lbl)

        # Click gesture
        gesture = Gtk.GestureClick()
        gesture.connect("pressed", lambda *_: self._on_cell_clicked(frame, media_path))
        overlay.add_controller(gesture)

        return overlay

    def _on_cell_clicked(self, frame: Gtk.Frame, path: str) -> None:
        """Handle a click on a thumbnail cell."""
        # Deselect all other cells in the current tab by removing the class
        # We walk the visible stack page children and reset them
        page = self._stack.get_visible_child()
        if page:
            self._deselect_all_in_widget(page)
        frame.add_css_class("picker-thumb-cell-selected")
        self._set_selection(path)

    def _deselect_all_in_widget(self, widget: Gtk.Widget) -> None:
        """Recursively remove picker-thumb-cell-selected from all descendants."""
        if widget.has_css_class("picker-thumb-cell"):
            widget.remove_css_class("picker-thumb-cell-selected")
        child = widget.get_first_child()
        while child:
            self._deselect_all_in_widget(child)
            child = child.get_next_sibling()

    def _set_selection(self, path: Optional[str]) -> None:
        self._selected_path = path
        self._use_btn.set_sensitive(path is not None)

    # ── Action handlers ───────────────────────────────────────────────────────

    def _on_use_clicked(self, _btn) -> None:
        if self._selected_path:
            self._on_select(self._selected_path)
        self.popdown()

    def _on_folder_chosen(self, dlg, result) -> None:
        try:
            gfile = dlg.select_folder_finish(result)
        except Exception:
            return
        path = gfile.get_path()
        if path:
            self._settings.set("motion_clips_dir", path)
            # Rebuild the disk page with the new folder
            disk_page = self._build_disk_page()
            old = self._stack.get_child_by_name("disk")
            if old:
                self._stack.remove(old)
            self._stack.add_named(disk_page, "disk")
            self._activate_tab("disk")

    def _on_browse_file(self, _btn) -> None:
        """Open a single-file FileDialog for a one-off pick."""
        dlg = Gtk.FileDialog()
        dlg.set_title("Select File")
        f = Gtk.FileFilter()
        f.set_name("Videos and Images")
        for pat in ("*.mp4", "*.mov", "*.avi", "*.webm", "*.mkv",
                    "*.png", "*.jpg", "*.jpeg", "*.webp"):
            f.add_pattern(pat)
        from gi.repository import Gio
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dlg.set_filters(store)
        dlg.open(None, None, self._on_browse_file_chosen)

    def _on_browse_file_chosen(self, dlg, result) -> None:
        try:
            gfile = dlg.open_finish(result)
        except Exception:
            return
        path = gfile.get_path()
        if path:
            self._on_select(path)
            self.popdown()
```

- [ ] **Step 2: Verify imports and syntax**

```bash
cd /home/ttuser/code/tt-local-generator
python -c "import sys; sys.path.insert(0,'app'); from animate_picker import PickerPopover; print('OK')"
```
Expected: `OK` (no errors).

- [ ] **Step 3: Run all tests**

```bash
python -m pytest tests/test_animate_picker.py -v
```
Expected: all pass (GTK-dependent tests may skip if no display).

- [ ] **Step 4: Commit**

```bash
git add app/animate_picker.py
git commit -m "feat: add PickerPopover with Bundled/Gallery/Disk tabs to animate_picker"
```

---

## Task 6: Wire `InputWidget` + `PickerPopover` into `ControlPanel`

Replace the existing "Motion Video" and "Character Image" rows (current `Gtk.Label` + `Gtk.Button(label="Browse…")` layout) with a horizontal pair of `InputWidget` instances. Each widget opens a `PickerPopover` on click.

**Files:**
- Modify: `app/main_window.py:2602-2668` (the `_animate_box` construction block inside `ControlPanel.__init__`)

- [ ] **Step 1: Add the import at the top of `main_window.py`**

Find the existing import block near line 42–48 and add:

```python
from animate_picker import InputWidget, PickerPopover
```

after the `from history_store import ...` line.

- [ ] **Step 2: Identify exact lines to replace**

Lines 2602–2641 build `_animate_box` with two rows: "Motion Video" (label + Browse button) and "Character Image" (label + Browse button). We replace only those two rows. The "Animation Mode" section (lines 2643–2668) stays unchanged.

The block to replace starts at:

```python
        self._animate_box.append(self._section("Motion Video"))
        mv_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._anim_video_lbl = Gtk.Label(label="none")
```

and ends just before:

```python
        self._animate_box.append(self._section("Animation Mode"))
```

- [ ] **Step 3: Replace the Motion Video + Character Image rows**

Replace lines 2613–2641 with the following. The `_anim_video_lbl` and `_anim_char_lbl` attributes are removed; new public methods `set_motion_input` and `set_char_input` replace them. The `_pick_ref_video` and `_pick_ref_image` methods remain as fallbacks but are no longer wired to buttons.

```python
        # ── Motion Video + Character inputs (side-by-side InputWidgets) ────────
        inputs_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._motion_input = InputWidget("motion", "MOTION VIDEO")
        self._char_input   = InputWidget("char",   "CHARACTER")

        inputs_row.append(self._motion_input)
        inputs_row.append(self._char_input)
        self._animate_box.append(inputs_row)

        # Wire click → open PickerPopover (created lazily on first click so
        # HistoryStore and settings are fully initialized by then).
        self._motion_picker: "PickerPopover | None" = None
        self._char_picker:   "PickerPopover | None" = None

        def _open_motion_picker(_btn):
            clips_dir = str(Path(__file__).parent / "assets" / "motion_clips")
            self._motion_picker = PickerPopover(
                widget_type="motion",
                clips_dir=clips_dir,
                history_records=self._store.all_records() if hasattr(self, "_store") else [],
                settings=_settings,
                on_select=self.set_motion_input,
            )
            self._motion_picker.set_parent(self._motion_input)
            self._motion_picker.popup()

        def _open_char_picker(_btn):
            clips_dir = str(Path(__file__).parent / "assets" / "motion_clips")
            self._char_picker = PickerPopover(
                widget_type="char",
                clips_dir=clips_dir,
                history_records=self._store.all_records() if hasattr(self, "_store") else [],
                settings=_settings,
                on_select=self.set_char_input,
            )
            self._char_picker.set_parent(self._char_input)
            self._char_picker.popup()

        self._motion_input.connect("clicked", _open_motion_picker)
        self._char_input.connect("clicked", _open_char_picker)
```

- [ ] **Step 4: Add `set_motion_input` and `set_char_input` public methods to `ControlPanel`**

These replace the old `_anim_video_lbl` / `_anim_char_lbl` label updates that were done inside `_ref_video_chosen` and `_ref_image_chosen`. Add them just before the `_pick_ref_video` method (around line 4123):

```python
    def set_motion_input(self, path: str) -> None:
        """Set the Motion Video InputWidget and internal ref_video_path."""
        self._ref_video_path = path
        self._motion_input.set_value(path)

    def set_char_input(self, path: str) -> None:
        """Set the Character InputWidget and internal ref_char_path."""
        self._ref_char_path = path
        self._char_input.set_value(path)
```

- [ ] **Step 5: Update `_ref_video_chosen` and `_ref_image_chosen` to delegate**

Replace the bodies of the two existing chosen callbacks so they call through to the new methods:

```python
    def _ref_video_chosen(self, dlg, result) -> None:
        try:
            gfile = dlg.open_finish(result)
        except Exception:
            return
        path = gfile.get_path()
        if path:
            self.set_motion_input(path)

    def _ref_image_chosen(self, dlg, result) -> None:
        try:
            gfile = dlg.open_finish(result)
        except Exception:
            return
        path = gfile.get_path()
        if path:
            self.set_char_input(path)
```

- [ ] **Step 6: Update the generation guard to use `_ref_video_path` / `_ref_char_path`**

At line ~4540, the animate source guard reads:

```python
            if not self._ref_video_path or not self._ref_char_path:
```

This still works because `set_motion_input` / `set_char_input` update those attributes. No change needed here.

- [ ] **Step 7: Remove now-unused `_anim_video_lbl` / `_anim_char_lbl` attribute references**

Search for any remaining references to `_anim_video_lbl` and `_anim_char_lbl` in the file and remove them:

```bash
grep -n "_anim_video_lbl\|_anim_char_lbl" app/main_window.py
```

Remove any lines found (there should be none after step 3 and 5 replacements; confirm with the grep).

- [ ] **Step 8: Smoke-test the app starts**

```bash
cd /home/ttuser/code/tt-local-generator
python -c "import sys; sys.path.insert(0,'app'); from main_window import ControlPanel; print('import OK')"
```
Expected: `import OK`.

- [ ] **Step 9: Commit**

```bash
git add app/main_window.py
git commit -m "feat: replace Browse file pickers with InputWidget pair in ControlPanel animate inputs"
```

---

## Task 7: Add mode toggle description bar

Add a `Gtk.Revealer(SLIDE_DOWN)` below the Animation/Replacement toggle that shows mode description text when the user hovers over a mode button.

**Files:**
- Modify: `app/main_window.py:2643-2664` (the mode toggle block inside `ControlPanel.__init__`)

- [ ] **Step 1: Add the description bar after the mode toggle**

After the `mode_row.append(self._anim_mode_repl_btn)` and `self._animate_box.append(mode_row)` lines (around line 2664), add:

```python
        # ── Mode description bar ───────────────────────────────────────────────
        # Slides down below the toggle on hover; stays anchored, never floats.
        self._mode_desc_revealer = Gtk.Revealer()
        self._mode_desc_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self._mode_desc_revealer.set_transition_duration(120)

        self._mode_desc_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._mode_desc_bar.add_css_class("mode-desc-bar")
        self._mode_desc_bar.set_margin_start(0)
        self._mode_desc_bar.set_margin_end(0)

        self._mode_desc_icon = Gtk.Label(label="💃")
        self._mode_desc_icon.add_css_class("mode-desc-bar-icon")
        self._mode_desc_icon.set_valign(Gtk.Align.START)

        desc_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self._mode_desc_text = Gtk.Label(label="")
        self._mode_desc_text.add_css_class("mode-desc-bar-text")
        self._mode_desc_text.set_xalign(0)
        self._mode_desc_text.set_wrap(True)
        self._mode_desc_text.set_hexpand(True)
        self._mode_desc_impact = Gtk.Label(label="")
        self._mode_desc_impact.set_xalign(0)
        self._mode_desc_impact.set_wrap(True)
        desc_text_box.append(self._mode_desc_text)
        desc_text_box.append(self._mode_desc_impact)

        self._mode_desc_bar.append(self._mode_desc_icon)
        self._mode_desc_bar.append(desc_text_box)
        self._mode_desc_revealer.set_child(self._mode_desc_bar)
        self._animate_box.append(self._mode_desc_revealer)

        # ── Hover wiring ───────────────────────────────────────────────────────
        # 200 ms leave delay prevents the bar from flashing when moving between buttons.
        self._mode_desc_leave_timer: "int | None" = None

        _ANIM_ICON = "💃"
        _ANIM_TEXT = (
            "Your character performs the motion from the reference video. "
            "Their appearance is preserved; only the movement is transferred."
        )
        _ANIM_IMPACT = "↳ Reference video sets the motion · Character appearance comes from your image"

        _REPL_ICON = "🔀"
        _REPL_TEXT = (
            "Your character replaces the person in the reference video. "
            "Motion, background, and timing come from the reference."
        )
        _REPL_IMPACT = "↳ Needs a visible person in the reference video · Background is preserved"

        def _show_mode_desc(icon: str, text: str, impact: str, css_variant: str) -> None:
            if self._mode_desc_leave_timer is not None:
                GLib.source_remove(self._mode_desc_leave_timer)
                self._mode_desc_leave_timer = None
            self._mode_desc_icon.set_label(icon)
            self._mode_desc_text.set_label(text)
            self._mode_desc_impact.set_label(impact)
            # Swap CSS class for correct accent colour
            self._mode_desc_bar.remove_css_class("mode-desc-bar-anim")
            self._mode_desc_bar.remove_css_class("mode-desc-bar-repl")
            self._mode_desc_bar.add_css_class(f"mode-desc-bar-{css_variant}")
            self._mode_desc_impact.remove_css_class("mode-desc-bar-impact-anim")
            self._mode_desc_impact.remove_css_class("mode-desc-bar-impact-repl")
            self._mode_desc_impact.add_css_class(f"mode-desc-bar-impact-{css_variant}")
            self._mode_desc_revealer.set_reveal_child(True)

        def _hide_mode_desc_delayed() -> None:
            def _do_hide() -> bool:
                self._mode_desc_revealer.set_reveal_child(False)
                self._mode_desc_leave_timer = None
                return GLib.SOURCE_REMOVE
            if self._mode_desc_leave_timer is not None:
                GLib.source_remove(self._mode_desc_leave_timer)
            self._mode_desc_leave_timer = GLib.timeout_add(200, _do_hide)

        for btn, icon, text, impact, variant in [
            (self._anim_mode_anim_btn, _ANIM_ICON, _ANIM_TEXT, _ANIM_IMPACT, "anim"),
            (self._anim_mode_repl_btn, _REPL_ICON, _REPL_TEXT, _REPL_IMPACT, "repl"),
        ]:
            mc = Gtk.EventControllerMotion()
            mc.connect("enter", lambda _c, _x, _y, i=icon, t=text, im=impact, v=variant:
                       _show_mode_desc(i, t, im, v))
            mc.connect("leave", lambda _c: _hide_mode_desc_delayed())
            btn.add_controller(mc)
```

- [ ] **Step 2: Add unit test for mode description bar toggle logic**

Append to `tests/test_animate_picker.py`:

```python
@gtk_required
def test_mode_desc_bar_reveal_logic():
    """Mode description bar CSS variant is set correctly for animation mode."""
    # We exercise the CSS-class helper logic directly without a full ControlPanel
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    bar = Gtk.Box()
    bar.add_css_class("mode-desc-bar")
    bar.remove_css_class("mode-desc-bar-anim")
    bar.remove_css_class("mode-desc-bar-repl")
    bar.add_css_class("mode-desc-bar-anim")
    assert bar.has_css_class("mode-desc-bar-anim")
    assert not bar.has_css_class("mode-desc-bar-repl")
    bar.remove_css_class("mode-desc-bar-anim")
    bar.add_css_class("mode-desc-bar-repl")
    assert bar.has_css_class("mode-desc-bar-repl")
    assert not bar.has_css_class("mode-desc-bar-anim")
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/test_animate_picker.py -v
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/main_window.py tests/test_animate_picker.py
git commit -m "feat: add inline mode description bar to Animation/Replacement toggle"
```

---

## Task 8: Add slide-up hover action bar to `GenerationCard`

Every `GenerationCard` gains a `Gtk.Revealer(SLIDE_UP)` overlay at the bottom of the thumbnail. The bar shows "💃 Animate" (teal) for all card types and "↗ Motion" (pink) for video/animate cards only. Callbacks are optional — cards constructed without them show no bar.

**Files:**
- Modify: `app/main_window.py:1117-1160` (`GenerationCard.__init__`)
- Modify: `app/main_window.py:1174-1240` (`GenerationCard._build`)

- [ ] **Step 1: Update `GenerationCard.__init__` to accept optional action callbacks**

Change the constructor signature from:

```python
    def __init__(self, record: GenerationRecord, iterate_cb, select_cb, delete_cb):
```

to:

```python
    def __init__(self, record: GenerationRecord, iterate_cb, select_cb, delete_cb,
                 animate_cb=None, motion_cb=None):
```

Store them:

```python
        self._animate_cb = animate_cb   # callable(record) or None
        self._motion_cb  = motion_cb    # callable(record) or None — None for image cards
```

Add these two lines just after `self._delete_cb = delete_cb`.

Also update the hover controller registration to cover all cards when either callback is present:

```python
        # Hover controller: plays video on hover (video cards) OR shows action bar
        has_hover = record.video_exists or animate_cb is not None or motion_cb is not None
        if has_hover:
            motion = Gtk.EventControllerMotion()
            motion.connect("enter", self._on_hover_enter)
            motion.connect("leave", self._on_hover_leave)
            self.add_controller(motion)
```

Replace the existing block (lines 1144–1150):

```python
        # Hovering over a video card plays it in the thumbnail area.
        # Image cards (FLUX) don't have a video to play, so no hover controller.
        if record.video_exists:
            motion = Gtk.EventControllerMotion()
            motion.connect("enter", self._on_hover_enter)
            motion.connect("leave", self._on_hover_leave)
            self.add_controller(motion)
```

- [ ] **Step 2: Add the action bar Revealer in `GenerationCard._build`**

At the end of `_build`, after `overlay.add_overlay(self._check)` (just before the media stack construction), add:

```python
        # ── Hover action bar ─────────────────────────────────────────────────
        # Gtk.Revealer(SLIDE_UP) overlaid at the bottom of the card thumbnail area.
        # Visible only when _animate_cb or _motion_cb is set.
        self._action_revealer = Gtk.Revealer()
        self._action_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_UP
        )
        self._action_revealer.set_transition_duration(150)
        self._action_revealer.set_valign(Gtk.Align.END)
        self._action_revealer.set_halign(Gtk.Align.FILL)

        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        action_bar.add_css_class("hover-action-bar")
        action_bar.set_hexpand(True)

        if self._animate_cb is not None:
            animate_btn = Gtk.Button(label="💃 Animate")
            animate_btn.add_css_class("hover-action-btn")
            animate_btn.add_css_class("hover-action-btn-animate")
            # Stop the gesture from propagating to the card's GestureClick (select)
            animate_btn.set_can_focus(False)
            animate_btn.connect(
                "clicked",
                lambda _b, rec=self._record: (
                    self._animate_cb(rec),
                    None,
                )[1],
            )
            action_bar.append(animate_btn)

        if self._motion_cb is not None and self._record.media_type == "video":
            motion_btn = Gtk.Button(label="↗ Motion")
            motion_btn.add_css_class("hover-action-btn")
            motion_btn.add_css_class("hover-action-btn-motion")
            motion_btn.set_can_focus(False)
            motion_btn.connect(
                "clicked",
                lambda _b, rec=self._record: (
                    self._motion_cb(rec),
                    None,
                )[1],
            )
            action_bar.append(motion_btn)

        self._action_revealer.set_child(action_bar)
        # Only add to overlay if at least one button is present
        if self._animate_cb is not None or self._motion_cb is not None:
            overlay.add_overlay(self._action_revealer)
```

- [ ] **Step 3: Update `_on_hover_enter` and `_on_hover_leave` to also toggle the action bar**

Find the existing `_on_hover_enter` and `_on_hover_leave` methods. Add revealer show/hide at the start/end of each:

In `_on_hover_enter` (currently starts the video), add at the very beginning:

```python
        if hasattr(self, "_action_revealer"):
            self._action_revealer.set_reveal_child(True)
```

In `_on_hover_leave`, add at the very beginning:

```python
        if hasattr(self, "_action_revealer"):
            self._action_revealer.set_reveal_child(False)
```

- [ ] **Step 4: Update `GalleryWidget.__init__` to accept and store action callbacks**

Change the constructor signature of `GalleryWidget` from:

```python
    def __init__(self, iterate_cb, select_cb, delete_cb, media_type: str = "video"):
```

to:

```python
    def __init__(self, iterate_cb, select_cb, delete_cb, media_type: str = "video",
                 animate_action_cb=None, motion_action_cb=None):
```

Store them:

```python
        self._animate_action_cb = animate_action_cb
        self._motion_action_cb  = motion_action_cb
```

- [ ] **Step 5: Update `GalleryWidget._make_card` to pass the callbacks**

Change:

```python
    def _make_card(self, record: GenerationRecord) -> "GenerationCard":
        return GenerationCard(
            record,
            iterate_cb=self._iterate_cb,
            select_cb=self.select_card,
            delete_cb=self._delete_cb,
        )
```

to:

```python
    def _make_card(self, record: GenerationRecord) -> "GenerationCard":
        return GenerationCard(
            record,
            iterate_cb=self._iterate_cb,
            select_cb=self.select_card,
            delete_cb=self._delete_cb,
            animate_cb=self._animate_action_cb,
            motion_cb=self._motion_action_cb,
        )
```

- [ ] **Step 6: Run the import smoke test**

```bash
python -c "import sys; sys.path.insert(0,'app'); from main_window import GenerationCard, GalleryWidget; print('OK')"
```
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add app/main_window.py
git commit -m "feat: add slide-up hover action bar to GenerationCard; wire through GalleryWidget"
```

---

## Task 9: Wire card action callbacks in `MainWindow`

Connect the gallery card action buttons to `ControlPanel.set_char_input` / `set_motion_input`. The "💃 Animate" action also switches the source selector to "animate".

**Files:**
- Modify: `app/main_window.py:5692-5703` (the `GalleryWidget` construction in `MainWindow._build_ui`)

- [ ] **Step 1: Add `_on_animate_card_action` and `_on_motion_card_action` methods to `MainWindow`**

Find the `MainWindow` class and add these methods near the other `_on_*` handlers (around line 6000):

```python
    def _on_animate_card_action(self, record: "GenerationRecord") -> None:
        """
        '💃 Animate' gallery card action.
        Switches to animate source and copies the card's thumbnail as the character image.
        The thumbnail is a first-frame still for videos — valid as a character seed.
        """
        # Switch to the animate source tab
        self._controls.switch_to_source("animate")
        # Set character image to the card's thumbnail
        char_path = record.thumbnail_path if record.thumbnail_exists else record.media_file_path
        if char_path and Path(char_path).exists():
            self._controls.set_char_input(char_path)
        # Flash status
        self._flash_status("Character set ✓")

    def _on_motion_card_action(self, record: "GenerationRecord") -> None:
        """
        '↗ Motion' gallery card action.
        Sets the card's video_path as the motion video input WITHOUT switching source.
        Only video/animate cards have this button (image cards don't).
        """
        if record.video_exists:
            self._controls.set_motion_input(record.video_path)
        self._flash_status("Motion set ✓")

    def _flash_status(self, message: str, duration_ms: int = 1500) -> None:
        """Show *message* in the status label for *duration_ms* ms, then restore."""
        current = self._status_lbl.get_label()
        self._status_lbl.set_label(message)
        def _restore() -> bool:
            if self._alive:
                self._status_lbl.set_label(current)
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(duration_ms, _restore)
```

- [ ] **Step 2: Pass the action callbacks when constructing the three GalleryWidgets**

Find the block around line 5692 that reads:

```python
        shared_cbs = dict(
            iterate_cb=self._controls.populate_prompts,
            select_cb=self._on_card_selected,
            delete_cb=self._on_delete_card,
        )
        self._video_gallery = GalleryWidget(**shared_cbs, media_type="video")
        self._animate_gallery = GalleryWidget(**shared_cbs, media_type="video")
        self._image_gallery = GalleryWidget(**shared_cbs, media_type="image")
```

Replace with:

```python
        shared_cbs = dict(
            iterate_cb=self._controls.populate_prompts,
            select_cb=self._on_card_selected,
            delete_cb=self._on_delete_card,
            animate_action_cb=self._on_animate_card_action,
            motion_action_cb=self._on_motion_card_action,
        )
        self._video_gallery   = GalleryWidget(**shared_cbs, media_type="video")
        self._animate_gallery = GalleryWidget(**shared_cbs, media_type="video")
        self._image_gallery   = GalleryWidget(**shared_cbs, media_type="image")
```

- [ ] **Step 3: Wire the `_store` reference into `ControlPanel` after construction**

The `ControlPanel._open_motion_picker` / `_open_char_picker` lambdas check `hasattr(self, "_store")` to get `HistoryStore.all_records()`. The store is attached as `self._controls._store = self._store` just after `ControlPanel` is constructed in `MainWindow._build_ui` (already present at line ~5633). No change needed — just confirm the line exists:

```bash
grep -n "_controls._store" app/main_window.py
```
Expected: one match showing `self._controls._store = self._store`.

- [ ] **Step 4: Add integration test for card actions**

Append to `tests/test_animate_picker.py`:

```python
@gtk_required
def test_gallery_card_action_callbacks_invoked():
    """Verify animate_cb and motion_cb are stored on GenerationCard."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
    from main_window import GenerationCard
    from history_store import GenerationRecord

    animate_calls = []
    motion_calls = []

    rec = GenerationRecord(
        id="test-0001", prompt="test", negative_prompt="",
        num_inference_steps=20, seed=42,
        video_path="/nonexistent/video.mp4",
        thumbnail_path="/nonexistent/thumb.jpg",
        created_at="2025-01-01T00:00:00",
        media_type="video",
    )

    card = GenerationCard(
        rec,
        iterate_cb=lambda r: None,
        select_cb=lambda c: None,
        delete_cb=lambda r: None,
        animate_cb=lambda r: animate_calls.append(r),
        motion_cb=lambda r: motion_calls.append(r),
    )

    # Simulate callbacks being invoked
    card._animate_cb(rec)
    card._motion_cb(rec)

    assert len(animate_calls) == 1
    assert len(motion_calls) == 1
    assert animate_calls[0].id == "test-0001"
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_animate_picker.py -v
```
Expected: all pass (GTK tests may skip if no display).

- [ ] **Step 6: Commit**

```bash
git add app/main_window.py tests/test_animate_picker.py
git commit -m "feat: wire gallery card animate/motion action callbacks through MainWindow"
```

---

## Task 10: Final polish and spec compliance check

- [ ] **Step 1: Verify `app/assets/motion_clips/` directory exists and is recognised**

```bash
ls app/assets/motion_clips/
```
Expected: at least the `gestures/` subdirectory visible.

- [ ] **Step 2: Verify `BundledClipScanner` picks up the gestures category**

```bash
python3 -c "
import sys; sys.path.insert(0,'app')
from animate_picker import BundledClipScanner
from pathlib import Path
clips_dir = Path('app/assets/motion_clips')
data = BundledClipScanner(str(clips_dir)).scan()
print('Categories:', list(data.keys()))
"
```
Expected: `Categories: ['gestures']` (at minimum; more once locomotion clips are added).

- [ ] **Step 3: Verify the app launches without import errors**

```bash
python -c "
import sys; sys.path.insert(0,'app')
import main_window
print('main_window import OK')
import animate_picker
print('animate_picker import OK')
"
```
Expected: two `OK` lines, no tracebacks.

- [ ] **Step 4: Run the full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all pre-existing tests still pass; new tests pass; no regressions.

- [ ] **Step 5: Commit any remaining fixups**

```bash
git add -p
git commit -m "chore: polish and spec compliance fixups for animate gallery integration"
```

---

## Self-Review Notes

**Spec coverage check:**

| Spec section | Plan task(s) |
|---|---|
| §1 Gallery Card Hover Actions (slide-up bar, callbacks) | Task 8, Task 9 |
| §2 InputWidget (replaces Browse buttons) | Task 4, Task 6 |
| §3 Three-Tab Popover Picker | Task 5, Task 6 |
| §4 Mode Toggle Description Bar | Task 7 |
| §5 Bundled Clips directory (scanner) | Task 3 |
| §6 Settings: Disk Folder | Task 1 |
| §7 Error Handling | Covered inline (grey placeholder on thumb fail, empty states, missing dir) |
| §8 Testing (unit + integration) | Tasks 3, 4, 7, 9 |

**Type consistency verified:**
- `InputWidget` named consistently throughout (`_motion_input`, `_char_input`)
- `PickerPopover` constructor args match usage in Task 6
- `set_motion_input(path)` / `set_char_input(path)` signatures match call sites in Task 9
- `GalleryWidget(animate_action_cb=..., motion_action_cb=...)` matches Task 8 definition
- `GenerationCard(animate_cb=..., motion_cb=...)` matches Task 8 definition

**Error handling coverage:**
- Thumbnail extraction fails → grey placeholder via `_show_placeholder("🎬")` in `InputWidget.set_value`
- Bundled clips directory missing → `BundledClipScanner.scan()` returns `{}`; Bundled tab shows "No bundled clips found."
- Gallery record file missing → `record.video_exists` / `record.thumbnail_exists` guards in `PickerPopover._build_gallery_page`
- Disk folder unreadable → `_populate_disk_grid` only runs when `Path(folder).is_dir()`
- Card action while server busy → inputs update immediately; user must wait for in-progress job to finish before submitting
