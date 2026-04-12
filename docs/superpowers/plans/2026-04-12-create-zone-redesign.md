# Create Zone Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the control panel's raw-parameter accordion and toolbar model buttons with a named, goal-oriented Create zone: CLIP LENGTH, QUALITY, and SHOT panels that auto-detect the running model and expose friendly controls instead of ML knobs.

**Architecture:** Extract generation configuration constants into a standalone `app/generation_config.py` (GTK-free, testable). Refactor `ControlPanel` to hold generation state as plain Python attributes (not spin-widget values), then build the new named-button UI on top. Move the Advanced accordion into a `Gtk.Window` dialog reached from the Generation menu.

**Tech Stack:** Python 3, GTK4 via PyGObject (`gi.repository.Gtk`, `GLib`), existing `app_settings.py` for persistence, `history_store.py` for "Repeat last" seed.

---

## File map

| File | Action | What changes |
|---|---|---|
| `app/generation_config.py` | **Create** | Pure tables: `CLIP_LENGTH_FRAMES`, `QUALITY_STEPS`, `clip_frames()`, `quality_steps()` |
| `app/app_settings.py` | **Modify** | Add `clip_length_slot`, `preferred_video_model`, `seed_mode`, `pinned_seed` defaults |
| `app/main_window.py` | **Modify** | Many sections — see per-task detail |
| `tests/test_generation_config.py` | **Create** | Tests for pure config functions |

`app/main_window.py` changes are broken into independent tasks by section — each one is self-contained and commits cleanly.

---

## Task 1: Extract generation config into a testable module

**Files:**
- Create: `app/generation_config.py`
- Create: `tests/test_generation_config.py`

This is the foundation every later task depends on. No GTK imports.

- [ ] **Write the failing tests**

```python
# tests/test_generation_config.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from generation_config import clip_frames, quality_steps, MODELS_WITH_FIXED_FRAMES

def test_clip_frames_wan2_standard():
    assert clip_frames("wan2", "standard") == 81

def test_clip_frames_wan2_short():
    assert clip_frames("wan2", "short") == 49

def test_clip_frames_wan2_long():
    assert clip_frames("wan2", "long") == 121

def test_clip_frames_wan2_extended():
    assert clip_frames("wan2", "extended") == 193

def test_clip_frames_skyreels_standard():
    assert clip_frames("skyreels", "standard") == 33

def test_clip_frames_skyreels_short():
    assert clip_frames("skyreels", "short") == 9

def test_clip_frames_skyreels_long():
    assert clip_frames("skyreels", "long") == 65

def test_clip_frames_skyreels_extended():
    assert clip_frames("skyreels", "extended") == 97

def test_clip_frames_unknown_slot_snaps_to_standard():
    assert clip_frames("wan2", "bogus") == 81

def test_clip_frames_unknown_model_returns_none():
    assert clip_frames("mochi", "standard") is None

def test_mochi_in_fixed_frames():
    assert "mochi" in MODELS_WITH_FIXED_FRAMES
    assert MODELS_WITH_FIXED_FRAMES["mochi"] == 168

def test_quality_steps_fast():
    assert quality_steps("fast") == 10

def test_quality_steps_standard():
    assert quality_steps("standard") == 30

def test_quality_steps_cinematic():
    assert quality_steps("cinematic") == 40

def test_quality_steps_unknown_returns_standard():
    assert quality_steps("bogus") == 30
```

- [ ] **Run to verify they fail**

```bash
cd ~/code/tt-local-generator
/usr/bin/python3 -m pytest tests/test_generation_config.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'generation_config'`

- [ ] **Implement `app/generation_config.py`**

```python
# app/generation_config.py
"""
Pure generation configuration tables — no GTK imports.

CLIP_LENGTH_FRAMES: maps (model_key, slot_name) -> frame_count
  model_key: "wan2" | "skyreels"
  slot_name: "short" | "standard" | "long" | "extended"
  Valid Wan2.2 counts follow 4k+1: 33, 49, 65, 81, 97, 121, 193…
  Valid SkyReels counts follow (N-1)%4==0: 9, 33, 65, 97…

MODELS_WITH_FIXED_FRAMES: models whose frame count is hard-coded in the runner
  and cannot be overridden via num_frames in the request.

CLIP_SLOTS: ordered list of slot names for display
QUALITY_PRESETS: ordered list of (slot_name, steps, label) tuples
"""

CLIP_LENGTH_FRAMES: dict[tuple[str, str], int] = {
    ("wan2",      "short"):    49,
    ("wan2",      "standard"): 81,
    ("wan2",      "long"):     121,
    ("wan2",      "extended"): 193,
    ("skyreels",  "short"):    9,
    ("skyreels",  "standard"): 33,
    ("skyreels",  "long"):     65,
    ("skyreels",  "extended"): 97,
}

# Models where the runner ignores num_frames — show a locked single button.
# Value is the hard-coded frame count so the UI can display it.
MODELS_WITH_FIXED_FRAMES: dict[str, int] = {
    "mochi": 168,   # TTMochi1Runner hard-codes num_frames=168; TODO: parameterise
}

CLIP_SLOTS: list[str] = ["short", "standard", "long", "extended"]

# (slot_name, inference_steps, display_label)
QUALITY_PRESETS: list[tuple[str, int, str]] = [
    ("fast",      10, "Fast"),
    ("standard",  30, "Standard"),
    ("cinematic", 40, "Cinematic"),
]

# Seconds per frame at 24 fps (used for display labels)
_FPS = 24


def clip_frames(model_key: str, slot: str) -> "int | None":
    """Return frame count for (model_key, slot), or None if model uses fixed frames.

    Returns the standard-slot value if slot is unrecognised.
    Returns None for models in MODELS_WITH_FIXED_FRAMES (use their fixed count instead).
    """
    if model_key in MODELS_WITH_FIXED_FRAMES:
        return None
    frames = CLIP_LENGTH_FRAMES.get((model_key, slot))
    if frames is None:
        frames = CLIP_LENGTH_FRAMES.get((model_key, "standard"))
    return frames


def quality_steps(slot: str) -> int:
    """Return inference step count for a quality slot name. Defaults to standard (30)."""
    for name, steps, _ in QUALITY_PRESETS:
        if name == slot:
            return steps
    return 30


def slot_for_steps(steps: int) -> "str | None":
    """Return the quality slot name for an exact step count, or None if no match."""
    for name, s, _ in QUALITY_PRESETS:
        if s == steps:
            return name
    return None


def clip_label(model_key: str, slot: str) -> str:
    """Human-readable sublabel for a CLIP LENGTH button, e.g. '3.4 s · 81 f'."""
    frames = clip_frames(model_key, slot)
    if frames is None:
        fixed = MODELS_WITH_FIXED_FRAMES.get(model_key, 0)
        return f"{fixed / _FPS:.1f} s · {fixed} f  (fixed)"
    secs = frames / _FPS
    return f"{secs:.1f} s · {frames} f"
```

- [ ] **Run tests — all should pass**

```bash
/usr/bin/python3 -m pytest tests/test_generation_config.py -v
```
Expected: 15 tests pass.

- [ ] **Commit**

```bash
cd ~/code/tt-local-generator
git add app/generation_config.py tests/test_generation_config.py
git commit -m "feat: add generation_config module (clip frames + quality steps tables)"
```

---

## Task 2: Add new settings keys to app_settings.py

**Files:**
- Modify: `app/app_settings.py`

- [ ] **Write the failing test**

```python
# Add to tests/test_app_settings.py (or create it if it doesn't exist)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

def test_new_create_zone_defaults():
    import importlib
    import app_settings
    importlib.reload(app_settings)
    d = app_settings.DEFAULTS
    assert d["clip_length_slot"] == "standard"
    assert d["preferred_video_model"] == ""
    assert d["seed_mode"] == "random"
    assert d["pinned_seed"] == -1
```

- [ ] **Run to verify it fails**

```bash
/usr/bin/python3 -m pytest tests/test_app_settings.py::test_new_create_zone_defaults -v 2>&1 | tail -10
```
Expected: `KeyError` or `AssertionError`.

- [ ] **Add defaults to `app/app_settings.py`**

Open `app/app_settings.py` and add after the existing `"skyreels_num_frames": 33,` line:

```python
    # Create zone — named control state
    "clip_length_slot":     "standard",  # "short"|"standard"|"long"|"extended"
    "preferred_video_model": "",          # "wan2"|"mochi"|"skyreels"|"" (auto)
    "seed_mode":            "random",    # "random"|"repeat"|"keep"
    "pinned_seed":          -1,          # used when seed_mode == "keep"
```

- [ ] **Run test — should pass**

```bash
/usr/bin/python3 -m pytest tests/test_app_settings.py::test_new_create_zone_defaults -v
```

- [ ] **Run full suite to check no regressions**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 tests pass.

- [ ] **Commit**

```bash
git add app/app_settings.py tests/test_app_settings.py
git commit -m "feat: add clip_length_slot, preferred_video_model, seed_mode, pinned_seed settings"
```

---

## Task 3: Refactor ControlPanel internal generation state to plain attributes

**Files:**
- Modify: `app/main_window.py` — `ControlPanel.__init__`, `ControlPanel._on_action_clicked`, `ControlPanel.get_generation_defaults`

Currently `_on_action_clicked` reads `self._steps_spin.get_value()` and `self._seed_spin.get_value()`. This task introduces plain attributes that act as the source of truth. Later tasks write to these attributes; the spin widgets in the Advanced dialog (Task 8) will also read/write them.

- [ ] **Add plain state attributes in `ControlPanel.__init__`** (around line 2198, after `self._seed_image_path = ""`):

```python
        # ── Generation state (source of truth for _on_action_clicked) ─────────
        # These replace direct spin-widget reads so the Advanced dialog and the
        # new named buttons can both drive the same values.
        self._steps: int = int(_settings.get("quality_steps") or 30)
        self._seed: int = -1          # -1 = random
        self._neg: str = ""
        self._guidance: float = 3.5
```

- [ ] **Update `_on_action_clicked`** to use plain attributes instead of spin widget reads.

Find this block (around line 4200):
```python
        args = (
            prompt,
            self._get_neg(),
            int(self._steps_spin.get_value()),
            int(self._seed_spin.get_value()),
```

Replace with:
```python
        args = (
            prompt,
            self._neg,
            self._steps,
            self._seed,
```

- [ ] **Update `get_generation_defaults`** (around line 4165):

Find:
```python
            "neg":            self._get_neg(),
            "steps":          int(self._steps_spin.get_value()),
            "seed":           int(self._seed_spin.get_value()),
```

Replace with:
```python
            "neg":            self._neg,
            "steps":          self._steps,
            "seed":           self._seed,
```

Find:
```python
            "guidance_scale": float(self._guidance_spin.get_value()),
```
Replace with:
```python
            "guidance_scale": self._guidance,
```

- [ ] **Update `_get_neg`** (around line 3892). This currently reads from a `TextView`. Keep it reading from the widget for now — the Advanced dialog (Task 8) will own that widget. Add a sync method instead:

After the existing `_get_neg` definition, add:
```python
    def _sync_neg_from_widget(self) -> None:
        """Called by AdvancedSettingsDialog when negative prompt changes."""
        buf = self._neg_prompt_tv.get_buffer()
        self._neg = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
```

- [ ] **Run the full test suite**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 tests pass (no test directly tests these private methods).

- [ ] **Smoke-test the app launches without error**

```bash
/usr/bin/python3 app/main.py &
sleep 3 && kill %1
```
Expected: no Python traceback printed.

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "refactor: ControlPanel generation state as plain attrs (_steps, _seed, _neg, _guidance)"
```

---

## Task 4: Remove model selector rows from toolbar; hide Animate tab

**Files:**
- Modify: `app/main_window.py` — `ControlPanel._build` and `ControlPanel.set_server_state`

The toolbar currently has two rows of model buttons (`_model_sel_row` and `_img_model_sel_row`) that get appended after the source tabs. Remove both. The `_video_model` and `_image_model` state variables stay — they're still used to pick which script to start and which model ID to pass to the worker.

- [ ] **Remove `_model_sel_row` construction block**

In `ControlPanel._build`, find and delete the following block (approx lines 2288–2323):

```python
        # ── Video model selector ──────────────────────────────────────────────
        self._model_sel_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._model_sel_row.set_margin_start(4)
        self._mdl_wan2_btn = Gtk.ToggleButton(label="Wan2.2")
        ...  # through to:
        self._model_sel_row.append(self._mdl_skyreels_btn)
```

Also delete:
```python
        # ── Image model selector ──────────────────────────────────────────────
        self._img_model_sel_row = Gtk.Box(...)
        ...  # through to:
        self._img_model_sel_row.set_visible(False)
```

And the two `self._toolbar_box.append(...)` lines that follow:
```python
        self._toolbar_box.append(self._model_sel_row)
        self._toolbar_box.append(self._img_model_sel_row)
```

- [ ] **Remove `_model_sel_row` visibility toggle in `_set_source`**

Search for `_model_sel_row.set_visible` and `_img_model_sel_row.set_visible` calls in `_set_source` (around line 3430). Delete those lines. The source switch should no longer touch model-row visibility.

- [ ] **Remove model button `set_active` calls from `set_server_state`**

Find the block in `set_server_state` (around line 3595) that calls:
```python
                    if video_key == "mochi":
                        self._mdl_mochi_btn.set_active(True)
                    elif video_key == "skyreels":
                        self._mdl_skyreels_btn.set_active(True)
                    else:
                        self._mdl_wan2_btn.set_active(True)
```

Replace it with:
```python
                    self._set_model(video_key)
```

(The `_set_model` method already sets `self._video_model` — that's all we need.)

- [ ] **Ensure Animate tab is hidden** (it already is; verify the line exists)

```bash
grep -n "src_animate_btn.*set_visible\|set_visible.*False.*animate" app/main_window.py
```
Expected output: one line containing `self._src_animate_btn.set_visible(False)`. If missing, add it after the animate button is created:
```python
        self._src_animate_btn.set_visible(False)  # hidden until model ships
```

- [ ] **Run full test suite**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 pass.

- [ ] **Launch app and verify toolbar**

```bash
/usr/bin/python3 app/main.py &
```
Toolbar should show: logo | Video / Image | (spacer) | Servers | Playlists | Watch. No Wan2.2/Mochi/SkyReels buttons.

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "feat: remove model selector buttons from toolbar; source tabs only"
```

---

## Task 5: Add QUALITY named buttons to ControlPanel

**Files:**
- Modify: `app/main_window.py` — `ControlPanel._build` (footer section), CSS block

Add a row of three named buttons (Fast / Standard / Cinematic) between the style chips and the Generate button. These replace the Advanced accordion's steps spinner as the primary quality control.

- [ ] **Add CSS for the named-button rows** (find the `/* -- Advanced accordion */` CSS block around line 485 and add before it):

```css
/* -- Named control rows (QUALITY, CLIP LENGTH) ------------------------------ */
.named-ctrl-row {
    margin-top: 2px;
    margin-bottom: 0;
}
.named-ctrl-btn {
    min-width: 0;
    padding: 5px 4px;
    border-radius: 0;
    font-size: 0.78em;
}
.named-ctrl-btn:first-child  { border-radius: 5px 0 0 5px; }
.named-ctrl-btn:last-child   { border-radius: 0 5px 5px 0; }
.named-ctrl-btn:checked,
.named-ctrl-btn.active       { background: alpha(@accent_color, 0.18);
                                color: @accent_color;
                                border-color: @accent_color; }
.named-ctrl-sub {
    font-size: 0.72em;
    opacity: 0.65;
    margin-top: 1px;
}
.create-zone-label {
    font-size: 0.7em;
    font-weight: bold;
    letter-spacing: 0.08em;
    opacity: 0.55;
    margin-top: 6px;
    margin-bottom: 1px;
}
```

- [ ] **Add `_build_quality_row()` method to `ControlPanel`** (add before `_build_servers_popover`, around line 2897):

```python
    def _build_quality_row(self) -> Gtk.Box:
        """QUALITY row: Fast / Standard / Cinematic named toggle buttons."""
        from generation_config import QUALITY_PRESETS, slot_for_steps

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        lbl = Gtk.Label(label="QUALITY  —  render detail & time")
        lbl.add_css_class("create-zone-label")
        lbl.set_xalign(0)
        outer.append(lbl)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("named-ctrl-row")

        self._quality_btns: list[Gtk.ToggleButton] = []
        first_btn = None
        current_steps = self._steps

        for slot, steps, display in QUALITY_PRESETS:
            btn = Gtk.ToggleButton()
            btn.steps_value = steps
            btn.slot_value = slot
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            inner.set_halign(Gtk.Align.CENTER)
            name_lbl = Gtk.Label(label=display)
            sub_lbl = Gtk.Label(label=f"~{steps // 10 * 3} min to render")
            sub_lbl.add_css_class("named-ctrl-sub")
            inner.append(name_lbl)
            inner.append(sub_lbl)
            btn.set_child(inner)
            btn.add_css_class("named-ctrl-btn")
            btn.set_hexpand(True)
            if first_btn is None:
                first_btn = btn
            else:
                btn.set_group(first_btn)
            if steps == current_steps or (slot_for_steps(current_steps) is None and slot == "standard"):
                btn.set_active(True)
            btn.connect("toggled", self._on_quality_btn_toggled)
            row.append(btn)
            self._quality_btns.append(btn)

        outer.append(row)
        return outer

    def _on_quality_btn_toggled(self, btn: Gtk.ToggleButton) -> None:
        if not btn.get_active():
            return
        self._steps = btn.steps_value
        _settings.set("quality_steps", self._steps)
        # Keep Advanced dialog in sync if open
        if hasattr(self, "_adv_dialog") and self._adv_dialog is not None:
            self._adv_dialog.sync_from_panel()

    def sync_quality_btn_to_steps(self, steps: int) -> None:
        """Called by AdvancedSettingsDialog when steps change to update the button state."""
        from generation_config import slot_for_steps, QUALITY_PRESETS
        self._steps = steps
        matched = False
        for btn in self._quality_btns:
            if btn.steps_value == steps:
                btn.set_active(True)
                matched = True
                break
        if not matched:
            # Show a "Custom" button or just leave no button active
            # For simplicity: none of the presets highlighted = user sees blank state
            for btn in self._quality_btns:
                btn.set_active(False)
```

- [ ] **Insert the quality row into `ControlPanel._build`** (find the `self._footer_box` construction — the section after chips and before the Advanced accordion — around line 2500):

Find where `self._footer_box` is built and the scrollable content ends. Add:
```python
        # ── Divider separating prompt from generation controls ─────────────────
        create_zone_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        create_zone_sep.set_margin_top(6)
        create_zone_sep.set_margin_bottom(2)
        scroll_inner.append(create_zone_sep)   # scroll_inner is the scrollable VBox

        # ── QUALITY row ───────────────────────────────────────────────────────
        self._quality_row_widget = self._build_quality_row()
        scroll_inner.append(self._quality_row_widget)
```

(Note: `scroll_inner` is the name of the `Gtk.Box` that holds scrollable content. Check the exact variable name in the code around line 2407–2420 with `grep -n "scroll_inner\|_scroll_box\|scrollable" app/main_window.py | head -20`.)

- [ ] **Verify the quality row hides for image source** — in `_set_source`, find where guidance widgets are hidden for video and add:

```python
        self._quality_row_widget.set_visible(is_video or is_animate)
```

- [ ] **Run tests**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 pass.

- [ ] **Launch app and verify** — Quality row appears below the chips for Video, is hidden for Image.

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "feat: add QUALITY named buttons (Fast/Standard/Cinematic) to Create zone"
```

---

## Task 6: Add CLIP LENGTH named buttons to ControlPanel

**Files:**
- Modify: `app/main_window.py` — `ControlPanel`

Add a CLIP LENGTH row above the QUALITY row. Buttons are model-specific (Wan2.2 vs SkyReels). Mochi shows a single locked button. Hidden for Image source.

- [ ] **Add `_build_clip_length_row()` method** (add alongside `_build_quality_row`):

```python
    def _build_clip_length_row(self) -> Gtk.Box:
        """CLIP LENGTH row — output video duration, model-specific frame counts."""
        from generation_config import CLIP_SLOTS, clip_label, MODELS_WITH_FIXED_FRAMES

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        lbl = Gtk.Label(label="CLIP LENGTH  —  output video is")
        lbl.add_css_class("create-zone-label")
        lbl.set_xalign(0)
        outer.append(lbl)

        self._clip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._clip_row.add_css_class("named-ctrl-row")
        outer.append(self._clip_row)

        # Mochi locked button (shown when mochi is active)
        self._clip_mochi_btn = Gtk.ToggleButton()
        self._clip_mochi_btn.set_active(True)
        self._clip_mochi_btn.set_sensitive(False)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.set_halign(Gtk.Align.CENTER)
        inner.append(Gtk.Label(label="7.0 s · 168 f  (fixed)"))
        self._clip_mochi_btn.set_child(inner)
        self._clip_mochi_btn.add_css_class("named-ctrl-btn")
        self._clip_mochi_btn.set_hexpand(True)
        self._clip_mochi_btn.set_visible(False)
        self._clip_row.append(self._clip_mochi_btn)

        # Normal slot buttons (shown for wan2 / skyreels)
        self._clip_btns: list[Gtk.ToggleButton] = []
        first_btn = None
        current_slot = str(_settings.get("clip_length_slot") or "standard")

        for slot in CLIP_SLOTS:
            btn = Gtk.ToggleButton()
            btn.slot_value = slot
            btn.add_css_class("named-ctrl-btn")
            btn.set_hexpand(True)
            if first_btn is None:
                first_btn = btn
            else:
                btn.set_group(first_btn)
            if slot == current_slot:
                btn.set_active(True)
            btn.connect("toggled", self._on_clip_btn_toggled)
            self._clip_row.append(btn)
            self._clip_btns.append(btn)

        # Set initial labels based on current video model
        self._refresh_clip_labels()
        outer.append(self._clip_row)
        return outer

    def _on_clip_btn_toggled(self, btn: Gtk.ToggleButton) -> None:
        if not btn.get_active():
            return
        _settings.set("clip_length_slot", btn.slot_value)

    def _refresh_clip_labels(self) -> None:
        """Update CLIP LENGTH button sublabels for the current video model."""
        from generation_config import CLIP_SLOTS, clip_label, MODELS_WITH_FIXED_FRAMES

        model_key = self._video_model   # "wan2" | "mochi" | "skyreels"
        is_fixed = model_key in MODELS_WITH_FIXED_FRAMES

        self._clip_mochi_btn.set_visible(is_fixed)
        for btn in self._clip_btns:
            btn.set_visible(not is_fixed)

        if not is_fixed:
            for btn, slot in zip(self._clip_btns, CLIP_SLOTS):
                slot_display = slot.capitalize()
                sublabel = clip_label(model_key, slot)
                inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                inner.set_halign(Gtk.Align.CENTER)
                inner.append(Gtk.Label(label=slot_display))
                sub = Gtk.Label(label=sublabel)
                sub.add_css_class("named-ctrl-sub")
                inner.append(sub)
                btn.set_child(inner)
```

- [ ] **Insert CLIP LENGTH row into `_build`** — add it just before the QUALITY row widget:

```python
        # ── CLIP LENGTH row ───────────────────────────────────────────────────
        self._clip_length_row_widget = self._build_clip_length_row()
        scroll_inner.append(self._clip_length_row_widget)
```

- [ ] **Call `_refresh_clip_labels()` when the model changes** — in `_set_model` (find around line 3520), add at the end of the method:

```python
        if hasattr(self, "_clip_btns"):
            self._refresh_clip_labels()
```

- [ ] **Hide CLIP LENGTH for Image source** — in `_set_source`, add:

```python
        self._clip_length_row_widget.set_visible(is_video or is_animate)
```

- [ ] **Run tests**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 pass.

- [ ] **Launch app — verify** CLIP LENGTH row appears for Video (Wan2.2: shows 4 slots with "2.0 s · 49 f" etc.). Switch to SkyReels — labels should update to SkyReels frame counts. Hidden for Image.

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "feat: add CLIP LENGTH named buttons (Short/Standard/Long/Extended) per model"
```

---

## Task 7: Add SHOT panel (model badge + switcher + seed variation)

**Files:**
- Modify: `app/main_window.py` — `ControlPanel`

The SHOT panel sits below QUALITY. It shows: auto-detected model badge, optional low-lift switcher hint, and three seed variation buttons.

- [ ] **Add CSS** (in the named-ctrl-rows CSS block added in Task 5):

```css
.shot-panel {
    border: 1px solid alpha(@borders, 0.5);
    border-radius: 6px;
    padding: 6px 8px;
    margin-top: 4px;
    margin-bottom: 2px;
}
.model-badge-label {
    font-size: 0.8em;
    font-weight: bold;
}
.model-badge-sub {
    font-size: 0.75em;
    opacity: 0.6;
}
.shot-switcher-btn {
    font-size: 0.72em;
    padding: 2px 6px;
    border-radius: 10px;
}
.seed-btn {
    min-width: 0;
    padding: 4px 4px;
    border-radius: 0;
    font-size: 0.78em;
}
.seed-btn:first-child { border-radius: 5px 0 0 5px; }
.seed-btn:last-child  { border-radius: 0 5px 5px 0; }
.seed-btn:checked,
.seed-btn.active      { background: alpha(#ec96b8, 0.18);
                        color: #ec96b8;
                        border-color: #ec96b8; }
```

- [ ] **Add `_build_shot_panel()` method**:

```python
    def _build_shot_panel(self) -> Gtk.Box:
        """SHOT panel: model badge + optional switcher + seed variation row."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        lbl = Gtk.Label(label="SHOT")
        lbl.add_css_class("create-zone-label")
        lbl.set_xalign(0)
        outer.append(lbl)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        panel.add_css_class("shot-panel")

        # ── Model row ─────────────────────────────────────────────────────────
        model_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._shot_model_lbl = Gtk.Label()
        self._shot_model_lbl.add_css_class("model-badge-label")
        self._shot_model_lbl.set_xalign(0)
        model_row.append(self._shot_model_lbl)

        self._shot_model_sub = Gtk.Label()
        self._shot_model_sub.add_css_class("model-badge-sub")
        self._shot_model_sub.set_xalign(0)
        model_row.append(self._shot_model_sub)

        _spacer = Gtk.Box()
        _spacer.set_hexpand(True)
        model_row.append(_spacer)

        # Switcher hint — shown when a second compatible model server is ready
        self._shot_switcher_btn = Gtk.Button()
        self._shot_switcher_btn.add_css_class("shot-switcher-btn")
        self._shot_switcher_btn.set_visible(False)
        self._shot_switcher_btn.connect("clicked", self._on_shot_switcher_clicked)
        model_row.append(self._shot_switcher_btn)

        panel.append(model_row)

        # ── Seed variation row ────────────────────────────────────────────────
        seed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self._seed_random_btn = Gtk.ToggleButton(label="🎲 New idea")
        self._seed_random_btn.add_css_class("seed-btn")
        self._seed_random_btn.set_hexpand(True)
        self._seed_random_btn.set_tooltip_text("Use a different random seed every time")

        self._seed_repeat_btn = Gtk.ToggleButton(label="🔁 Repeat last")
        self._seed_repeat_btn.add_css_class("seed-btn")
        self._seed_repeat_btn.set_hexpand(True)
        self._seed_repeat_btn.set_tooltip_text("Re-use the seed from the most recent generation")
        self._seed_repeat_btn.set_group(self._seed_random_btn)

        self._seed_keep_btn = Gtk.ToggleButton(label="📌 Keep this")
        self._seed_keep_btn.add_css_class("seed-btn")
        self._seed_keep_btn.set_hexpand(True)
        self._seed_keep_btn.set_tooltip_text("Pin the current seed value across all generations")
        self._seed_keep_btn.set_group(self._seed_random_btn)

        self._seed_random_btn.connect("toggled", lambda b: b.get_active() and self._on_seed_mode("random"))
        self._seed_repeat_btn.connect("toggled", lambda b: b.get_active() and self._on_seed_mode("repeat"))
        self._seed_keep_btn.connect("toggled", lambda b: b.get_active() and self._on_seed_mode("keep"))

        seed_row.append(self._seed_random_btn)
        seed_row.append(self._seed_repeat_btn)
        seed_row.append(self._seed_keep_btn)
        panel.append(seed_row)

        # Initialise from settings
        self._apply_seed_mode_from_settings()
        outer.append(panel)
        return outer

    def _apply_seed_mode_from_settings(self) -> None:
        """Set the seed variation button state and self._seed from saved settings."""
        from history_store import HistoryStore
        mode = str(_settings.get("seed_mode") or "random")
        if mode == "repeat":
            # Check history is non-empty; fall back to random if empty
            try:
                recs = self._store.all_records() if hasattr(self, "_store") else []
            except Exception:
                recs = []
            if recs:
                last_seed = getattr(sorted(recs, key=lambda r: getattr(r, "created_at", ""))[-1], "seed", -1)
                self._seed = int(last_seed) if last_seed is not None else -1
                self._seed_repeat_btn.set_active(True)
            else:
                self._seed = -1
                self._seed_random_btn.set_active(True)
                self._seed_repeat_btn.set_sensitive(False)
        elif mode == "keep":
            self._seed = int(_settings.get("pinned_seed") or -1)
            self._seed_keep_btn.set_active(True)
        else:
            self._seed = -1
            self._seed_random_btn.set_active(True)

        # Grey out "Repeat last" if no history
        try:
            recs = self._store.all_records() if hasattr(self, "_store") else []
        except Exception:
            recs = []
        self._seed_repeat_btn.set_sensitive(bool(recs))

    def _on_seed_mode(self, mode: str) -> None:
        _settings.set("seed_mode", mode)
        if mode == "random":
            self._seed = -1
        elif mode == "repeat":
            try:
                recs = sorted(
                    self._store.all_records(),
                    key=lambda r: getattr(r, "created_at", "")
                )
                last = recs[-1] if recs else None
                self._seed = int(getattr(last, "seed", -1) or -1) if last else -1
            except Exception:
                self._seed = -1
        elif mode == "keep":
            pinned = int(_settings.get("pinned_seed") or -1)
            self._seed = pinned if pinned != -1 else self._seed
            _settings.set("pinned_seed", self._seed)
            self._seed_keep_btn.set_label(f"📌 {self._seed}" if self._seed != -1 else "📌 Keep this")

    def _on_shot_switcher_clicked(self, _btn) -> None:
        """Switch to the alternate ready model without restarting anything."""
        alt = getattr(self, "_shot_alt_model_key", None)
        if alt:
            self._set_model(alt)
            _settings.set("preferred_video_model", alt)
            self.update_shot_panel()

    def update_shot_panel(self) -> None:
        """Refresh the model badge and switcher hint. Called by health updates."""
        if not hasattr(self, "_shot_model_lbl"):
            return
        model_key = self._video_model
        source = self._model_source

        # Model display names and resolution hints
        _DISPLAY = {
            "wan2":     ("● Wan2.2",     "720p"),
            "mochi":    ("● Mochi-1",    "480×848"),
            "skyreels": ("● SkyReels",   "480×272"),
        }
        _OFFLINE = "○ No server · Start one ›"

        if source != "video":
            # Image: just show FLUX
            self._shot_model_lbl.set_label("● FLUX.1-dev")
            self._shot_model_sub.set_label("image")
            self._shot_switcher_btn.set_visible(False)
            return

        server_ready = getattr(self, "_shot_server_ready", False)
        if not server_ready:
            self._shot_model_lbl.set_label(_OFFLINE)
            self._shot_model_sub.set_label("")
            self._shot_switcher_btn.set_visible(False)
            return

        name, res = _DISPLAY.get(model_key, (f"● {model_key}", ""))
        self._shot_model_lbl.set_label(name)
        self._shot_model_sub.set_label(res)

        # Show switcher if an alternate video model server is also ready
        alt_key = getattr(self, "_shot_alt_model_key", None)
        if alt_key:
            alt_name = _DISPLAY.get(alt_key, (alt_key,))[0].lstrip("● ")
            self._shot_switcher_btn.set_label(f"{alt_name} also ready ›")
            self._shot_switcher_btn.set_visible(True)
        else:
            self._shot_switcher_btn.set_visible(False)
```

- [ ] **Insert SHOT panel into `_build`** (after `_quality_row_widget`):

```python
        # ── SHOT panel ────────────────────────────────────────────────────────
        self._shot_panel_widget = self._build_shot_panel()
        scroll_inner.append(self._shot_panel_widget)
```

- [ ] **Wire up health updates to the SHOT panel** — in `MainWindow._on_health_result` (find around line 5850), add at the end of the method:

```python
        # Update SHOT panel model badge and switcher
        # Determine which video model keys are currently ready
        ready_video_keys = []
        for srv_key in ("wan2.2", "mochi", "skyreels"):
            if health_map.get(srv_key):
                # Map service key to model key used by ControlPanel
                mk = {"wan2.2": "wan2", "mochi": "mochi", "skyreels": "skyreels"}.get(srv_key)
                if mk:
                    ready_video_keys.append(mk)
        active = self._controls._video_model
        self._controls._shot_server_ready = active in ready_video_keys or bool(ready_video_keys)
        # If preferred model not ready but another is, auto-switch
        pref = str(_settings.get("preferred_video_model") or "")
        if pref and pref in ready_video_keys:
            self._controls._set_model(pref)
        elif ready_video_keys and active not in ready_video_keys:
            self._controls._set_model(ready_video_keys[0])
        # Alternate model for switcher hint
        others = [k for k in ready_video_keys if k != self._controls._video_model]
        self._controls._shot_alt_model_key = others[0] if others else None
        GLib.idle_add(self._controls.update_shot_panel)
```

Note: `health_map` is the dict of `{service_key: bool}` returned by `status_all()`. Check the actual variable name used in `_on_health_result` and adapt the above accordingly.

- [ ] **Run tests**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 pass.

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "feat: add SHOT panel with model badge, switcher hint, and seed variation"
```

---

## Task 8: Move seed image thumbnail inline with Inspire row

**Files:**
- Modify: `app/main_window.py` — `ControlPanel._build` (Inspire row section)

The seed image browse/clear currently lives inside the Advanced accordion. Move it to a small thumbnail well beside the Inspire me button.

- [ ] **Find the Inspire row construction** (around line 2430). Currently:

```python
        inspire_row.append(self._inspire_btn)
```

Add a seed thumbnail drop target before the inspire button:

```python
        # Seed image well — drag a gallery thumbnail here to use as seed
        self._seed_thumb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._seed_thumb_box.set_size_request(40, 40)
        self._seed_thumb_box.set_tooltip_text(
            "Drop a gallery frame here to use as the seed image\n"
            "Click to browse, right-click to clear"
        )
        self._seed_thumb_box.add_css_class("seed-thumb-well")

        self._seed_thumb_lbl = Gtk.Label(label="🖼")
        self._seed_thumb_lbl.set_vexpand(True)
        self._seed_thumb_lbl.set_valign(Gtk.Align.CENTER)
        self._seed_thumb_box.append(self._seed_thumb_lbl)

        thumb_click = Gtk.GestureClick()
        thumb_click.connect("released", lambda g, n, x, y: self._pick_seed_image(None))
        self._seed_thumb_box.add_controller(thumb_click)

        inspire_row.append(self._seed_thumb_box)
        inspire_row.append(self._inspire_btn)
```

- [ ] **Add CSS** for the seed thumbnail well (add to named-ctrl-rows CSS block):

```css
.seed-thumb-well {
    border: 1px dashed alpha(@borders, 0.7);
    border-radius: 5px;
    min-width: 36px;
    min-height: 36px;
    cursor: pointer;
}
.seed-thumb-well.has-seed {
    border-style: solid;
    border-color: @accent_color;
}
```

- [ ] **Update `_set_seed_image`** to also update the thumbnail well (find `_set_seed_image` around line 3756):

```python
    def _set_seed_image(self, path: str) -> None:
        self._seed_image_path = path
        # Update thumbnail well
        if hasattr(self, "_seed_thumb_box"):
            if path:
                img = _make_image_widget(path, 36, 36)
                # Replace the label with the image
                child = self._seed_thumb_box.get_first_child()
                if child:
                    self._seed_thumb_box.remove(child)
                self._seed_thumb_box.append(img)
                self._seed_thumb_box.add_css_class("has-seed")
            else:
                child = self._seed_thumb_box.get_first_child()
                if child:
                    self._seed_thumb_box.remove(child)
                lbl = Gtk.Label(label="🖼")
                lbl.set_vexpand(True)
                lbl.set_valign(Gtk.Align.CENTER)
                self._seed_thumb_box.append(lbl)
                self._seed_thumb_box.remove_css_class("has-seed")
        # Also update existing Advanced accordion display if present
        if hasattr(self, "_seed_thumb_lbl_adv"):
            self._seed_thumb_lbl_adv.set_label(
                Path(path).name if path else "No image selected"
            )
```

- [ ] **Update `_clear_seed_image`** to delegate to `_set_seed_image`:

```python
    def _clear_seed_image(self) -> None:
        self._set_seed_image("")
```

- [ ] **Run tests and launch** — seed thumbnail well should appear beside Inspire me, clicking it opens the file dialog, an image appears as a small preview.

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "feat: move seed image thumbnail well inline with Inspire me row"
```

---

## Task 9: Extract Advanced accordion into a dialog; add Generation menu item

**Files:**
- Modify: `app/main_window.py` — add `AdvancedSettingsDialog`, update `_build_menu_bar`, update `MainWindow` action wiring

The existing accordion widgets (`_adv_revealer`, `_adv_hdr_btn`, `_steps_spin`, `_seed_spin`, `_guidance_spin`, `_neg_prompt_tv`, seed image section) are relocated into a simple non-modal `Gtk.Window`. The accordion body is removed from `ControlPanel._footer_box`.

- [ ] **Add `AdvancedSettingsDialog` class** (add before `PreferencesDialog`, around line 4773):

```python
class AdvancedSettingsDialog(Gtk.Window):
    """Non-modal dialog exposing raw generation parameters for advanced users.

    Reads initial values from the ControlPanel's plain state attributes and
    writes back to them on every change, keeping the named buttons in sync.
    """

    def __init__(self, panel: "ControlPanel"):
        super().__init__()
        self._panel = panel
        self.set_title("Advanced Generation Settings")
        self.set_default_size(340, 320)
        self.set_resizable(False)
        app = panel.get_root().get_application() if panel.get_root() else None
        if app:
            self.set_application(app)
        self.set_transient_for(panel.get_root())
        self._build()

    def _build(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        self.set_child(box)

        # ── Steps ─────────────────────────────────────────────────────────────
        steps_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        steps_lbl = Gtk.Label(label="Inference steps (10–50):")
        steps_lbl.set_xalign(0)
        steps_lbl.set_hexpand(True)
        steps_row.append(steps_lbl)
        self._steps_spin = Gtk.SpinButton()
        self._steps_spin.set_adjustment(Gtk.Adjustment(
            value=self._panel._steps, lower=10, upper=50, step_increment=1, page_increment=10))
        self._steps_spin.connect("value-changed", self._on_steps_changed)
        steps_row.append(self._steps_spin)
        box.append(steps_row)

        # ── Seed ──────────────────────────────────────────────────────────────
        seed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        seed_lbl = Gtk.Label(label="Seed (−1 = random):")
        seed_lbl.set_xalign(0)
        seed_lbl.set_hexpand(True)
        seed_row.append(seed_lbl)
        self._seed_spin = Gtk.SpinButton()
        self._seed_spin.set_adjustment(Gtk.Adjustment(
            value=self._panel._seed, lower=-1, upper=2**31 - 1, step_increment=1, page_increment=1000))
        self._seed_spin.connect("value-changed", self._on_seed_changed)
        seed_row.append(self._seed_spin)
        box.append(seed_row)

        # ── Guidance scale ────────────────────────────────────────────────────
        self._guidance_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        guidance_lbl = Gtk.Label(label="Guidance scale (1–20):")
        guidance_lbl.set_xalign(0)
        guidance_lbl.set_hexpand(True)
        self._guidance_row.append(guidance_lbl)
        self._guidance_spin = Gtk.SpinButton()
        self._guidance_spin.set_adjustment(Gtk.Adjustment(
            value=self._panel._guidance, lower=1.0, upper=20.0, step_increment=0.5, page_increment=1.0))
        self._guidance_spin.set_digits(1)
        self._guidance_spin.connect("value-changed", self._on_guidance_changed)
        self._guidance_row.append(self._guidance_spin)
        box.append(self._guidance_row)

        # ── Negative prompt ───────────────────────────────────────────────────
        neg_lbl = Gtk.Label(label="Negative prompt:")
        neg_lbl.set_xalign(0)
        box.append(neg_lbl)
        self._neg_tv = Gtk.TextView()
        self._neg_tv.set_wrap_mode(Gtk.WrapMode.WORD)
        self._neg_tv.set_size_request(-1, 60)
        self._neg_tv.get_buffer().set_text(self._panel._neg)
        self._neg_tv.get_buffer().connect("changed", self._on_neg_changed)
        neg_scroll = Gtk.ScrolledWindow()
        neg_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        neg_scroll.set_child(self._neg_tv)
        neg_scroll.set_size_request(-1, 68)
        box.append(neg_scroll)

    def _on_steps_changed(self, spin: Gtk.SpinButton) -> None:
        steps = int(spin.get_value())
        self._panel.sync_quality_btn_to_steps(steps)  # updates _panel._steps too

    def _on_seed_changed(self, spin: Gtk.SpinButton) -> None:
        self._panel._seed = int(spin.get_value())
        # Update seed mode to "keep" with the new value
        _settings.set("pinned_seed", self._panel._seed)
        if hasattr(self._panel, "_seed_keep_btn"):
            self._panel._seed_keep_btn.set_active(True)
            self._panel._seed_keep_btn.set_label(
                f"📌 {self._panel._seed}" if self._panel._seed != -1 else "📌 Keep this"
            )

    def _on_guidance_changed(self, spin: Gtk.SpinButton) -> None:
        self._panel._guidance = float(spin.get_value())

    def _on_neg_changed(self, buf: Gtk.TextBuffer) -> None:
        self._panel._neg = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def sync_from_panel(self) -> None:
        """Refresh dialog widgets from panel state (called when Quality buttons change)."""
        self._steps_spin.set_value(self._panel._steps)
        self._seed_spin.set_value(self._panel._seed)
        self._guidance_spin.set_value(self._panel._guidance)
        self._guidance_row.set_visible(self._panel._model_source == "image")
```

- [ ] **Add `_adv_dialog` attribute and opener to `ControlPanel`** — in `ControlPanel.__init__` (after the new plain attrs from Task 3):

```python
        self._adv_dialog: "AdvancedSettingsDialog | None" = None
```

Add an opener method:
```python
    def open_advanced_dialog(self) -> None:
        """Open or present the Advanced Settings dialog."""
        if self._adv_dialog is None or not self._adv_dialog.get_visible():
            self._adv_dialog = AdvancedSettingsDialog(self)
        self._adv_dialog.present()
```

- [ ] **Add "Advanced…" to the Generation menu** — in `_build_menu_bar` (around line 5491), after the sleep section:

```python
        adv_section = Gio.Menu()
        adv_section.append("Advanced Settings…", "win.advanced-settings")
        gen_menu.append_section(None, adv_section)
```

- [ ] **Register the `win.advanced-settings` action** — in `MainWindow._register_actions` (or wherever other `win.*` actions are registered; search for `Gio.SimpleAction` around line 5400):

```python
        adv_action = Gio.SimpleAction.new("advanced-settings", None)
        adv_action.connect("activate", lambda a, p: self._controls.open_advanced_dialog())
        self.add_action(adv_action)
```

- [ ] **Remove the Advanced accordion from `ControlPanel._footer_box`** — find and delete the block that appends `self._adv_revealer` to `self._footer_box` (around line 2744). Also remove the `_adv_hdr_btn`, `_adv_revealer`, `_adv_summary_box`, `_adv_arrow_lbl` construction blocks (lines ~2508–2749). Remove `_on_adv_toggle` and `_update_adv_summary` methods.

Keep `_neg_prompt_tv` only if it is referenced elsewhere. If it was only in the accordion, remove it and rely on `AdvancedSettingsDialog._neg_tv` instead. Remove `_pick_seed_image` references that pointed to the accordion seed section — the seed well is now in the Inspire row (Task 8).

- [ ] **Run tests**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 pass.

- [ ] **Launch — verify** the Advanced accordion is gone from the panel. Generation → Advanced Settings… opens a small window with steps, seed, guidance, negative prompt.

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "feat: move Advanced Settings into dialog; add Generation menu item"
```

---

## Task 10: Wire `_on_generate` to use clip_length_slot; update PreferencesDialog

**Files:**
- Modify: `app/main_window.py` — `MainWindow._on_generate`, `PreferencesDialog._build`

- [ ] **Update `_on_generate`** — replace the `skyreels_num_frames` / `wan_num_frames` settings reads with the new `clip_length_slot`:

Find (around line 6276):
```python
            num_frames_arg: "int | None" = None
            if model_name in ("skyreels-v2-1.3b-540p",
                              "Skywork/SkyReels-V2-DF-1.3B-540P-Diffusers"):
                num_frames_arg = int(_settings.get("skyreels_num_frames") or 33)
            elif model_name in ("wan2.2-t2v", "wan2.2-animate-14b"):
                num_frames_arg = int(_settings.get("wan_num_frames") or 81)
```

Replace with:
```python
            from generation_config import clip_frames, MODELS_WITH_FIXED_FRAMES
            num_frames_arg: "int | None" = None
            video_model_key = self._controls._video_model   # "wan2"|"mochi"|"skyreels"
            slot = str(_settings.get("clip_length_slot") or "standard")
            if video_model_key in MODELS_WITH_FIXED_FRAMES:
                num_frames_arg = None   # runner ignores it anyway
            else:
                num_frames_arg = clip_frames(video_model_key, slot)
```

- [ ] **Remove the Wan2.2 and SkyReels frame-count sections from `PreferencesDialog._build`**

Find and delete the "Video duration (WAN 2.2)" row block (including the `wan_durations` list, `wan_frames_drop`, and `box.append(self._row(...))` call) and the entire "SkyReels" section that follows it (including `skyreels_durations`, `sr_frames_drop`, and its `box.append`). These settings are now controlled by the CLIP LENGTH row in the panel.

Also remove the "Quality" radio section from `PreferencesDialog._build` (the `quality_btns` radio group) since quality is now controlled by the QUALITY row in the panel.

- [ ] **Run full test suite**

```bash
/usr/bin/python3 -m pytest tests/ -q
```
Expected: all 107 pass.

- [ ] **End-to-end smoke test**

```bash
# Start a server if available, otherwise just confirm the app opens cleanly
/usr/bin/python3 app/main.py &
# In the UI:
# 1. Select Video → Wan2.2 server (if running): CLIP LENGTH updates to 4k+1 counts
# 2. Click "Short" → generates with 49 frames
# 3. Click "Cinematic" → _steps becomes 40
# 4. Generation → Advanced Settings → change steps to 25 → panel shows no preset highlighted
# 5. Open Preferences → no quality radio, no frame dropdowns
```

- [ ] **Commit**

```bash
git add app/main_window.py
git commit -m "feat: wire _on_generate to clip_length_slot; remove frame dropdowns and quality radio from Preferences"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Remove model selector rows from toolbar | Task 4 |
| Hide Animate tab | Task 4 |
| CLIP LENGTH named buttons, model-specific sublabels | Task 6 |
| QUALITY named buttons with "to render" sublabels | Task 5 |
| SHOT panel: model badge, switcher hint, seed variation | Task 7 |
| Seed thumbnail inline with Inspire me | Task 8 |
| Advanced Settings moved to Generation menu | Task 9 |
| Bidirectional sync Advanced ↔ named buttons | Task 9 (`sync_from_panel`, `sync_quality_btn_to_steps`) |
| Mochi locked CLIP LENGTH button | Task 6 (`_clip_mochi_btn`) |
| `preferred_video_model` setting | Task 2 + Task 7 (`_on_shot_switcher_clicked`) |
| `seed_mode` / `pinned_seed` / `clip_length_slot` settings | Task 2 |
| Remove quality radio from Preferences | Task 10 |
| Remove SkyReels / Wan frame dropdowns from Preferences | Task 10 |
| `_on_generate` reads `clip_length_slot` | Task 10 |
| `generation_config.py` pure tables | Task 1 |

All spec requirements are covered.

**Placeholder scan:** No TBDs or "implement later" items. All code blocks are complete.

**Type consistency:** `clip_frames(model_key, slot)` returns `int | None` consistently across Task 1 definition and Task 6/10 call sites. `quality_steps(slot)` returns `int`. `sync_quality_btn_to_steps(steps: int)` defined in Task 5, called in Task 9 `AdvancedSettingsDialog._on_steps_changed` — consistent.

**Note on `scroll_inner` variable name:** Task 5 and 6 reference `scroll_inner` as the scrollable box in `ControlPanel._build`. Verify the actual variable name before implementing — run:
```bash
grep -n "scroll_inner\|_scroll_box\|VBox\|scroll.*box\|box.*scroll" app/main_window.py | grep -i "inner\|content\|body" | head -10
```
and substitute the correct name in the `append` calls.
