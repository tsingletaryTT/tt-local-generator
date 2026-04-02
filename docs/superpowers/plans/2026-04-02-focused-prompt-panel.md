# Focused Prompt Panel + Server Model Awareness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the control panel so the prompt dominates the visible area, hide advanced settings in an accordion, move animate inputs above the accordion, and extend the health worker to detect the running model and reflect match/mismatch state in a redesigned server row.

**Architecture:** All changes are in `api_client.py` (one new method) and `main_window.py` (CSS additions, `_build()` restructure, new accordion widget, server row replacement, `set_server_ready()` → `set_server_state()`, health worker extension). No new files. No tests needed — all changes are UI-only; existing 21 tests must still pass.

**Tech Stack:** Python 3, GTK4/PyGObject, `Gtk.Revealer` (SLIDE_DOWN accordion), `GLib.idle_add()` for threading.

**Spec:** `docs/superpowers/specs/2026-04-02-focused-prompt-panel-design.md`

---

## File Map

| File | Change |
|------|--------|
| `api_client.py` | Add `detect_running_model() -> str \| None` method to `APIClient` |
| `main_window.py` | CSS: add 3 new rule blocks; `_build()`: taller prompt, move neg/params/seed into accordion, move animate_box, add accordion widget, replace server row; add `_on_adv_toggle()`, `_update_adv_summary()`, `_apply_server_row_style()`, `set_server_state()`, `_on_switch_to_running_model_tab()`, `switch_to_source()`; `__init__`: add `_running_model`, `_adv_open`; module-level `_MODEL_TO_SOURCE`/`_MODEL_DISPLAY_SERVER`; `MainWindow.__init__`: add `_auto_tab_switched`; `_health_loop()`: call `detect_running_model()`; `_on_health_result()`: auto tab-switch + call `set_server_state()`; remove `set_server_ready()` |

---

## Task 1: `detect_running_model()` in `api_client.py`

**Files:**
- Modify: `api_client.py`

Add a new method to `APIClient` that queries `/v1/models` and returns the first model ID string, or `None` on any error.

- [ ] **Step 1: Add `detect_running_model()` method**

In `api_client.py`, after the `health_check()` method (after line 112), insert:

```python
def detect_running_model(self) -> "str | None":
    """
    Query the server for its loaded model ID.

    Tries GET /v1/models (OpenAI-compatible endpoint). Returns the first
    model ID string from data[0].id, or None if the endpoint is absent,
    the response is malformed, or a network error occurs.

    Never raises — all failures return None.
    """
    try:
        resp = requests.get(
            f"{self.base_url}/v1/models",
            timeout=5,
            headers=self._headers(),
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", [])
        if data:
            return data[0].get("id")
        return None
    except Exception:
        return None
```

- [ ] **Step 2: Run existing tests to confirm no regressions**

```bash
cd /home/ttuser/code/tt-local-generator
python3 -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all 21 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /home/ttuser/code/tt-local-generator
git add api_client.py
git commit -m "feat: add detect_running_model() to APIClient"
```

---

## Task 2: CSS additions for accordion and server row states

**Files:**
- Modify: `main_window.py` (the `_CSS` bytes literal, starting around line 42)

Add three CSS blocks to `_CSS`. Find the end of the `_CSS` block (the closing `"""`) and insert before it.

- [ ] **Step 1: Read the end of `_CSS` to find exact insertion point**

Read `main_window.py` around lines 290–315 to confirm the last lines of `_CSS` before the closing `"""`.

- [ ] **Step 2: Add server row CSS classes**

In `main_window.py`, find the closing `"""` of the `_CSS` bytes literal and insert before it:

```css
/* ── Server row states ───────────────────────────────────────────────────── */
.server-row-match {
    background-color: @tt_bg_darkest;
    border: 1px solid alpha(@tt_accent, 0.4);
    border-radius: 4px;
    padding: 5px 6px;
}
.server-row-mismatch {
    background-color: #1A1000;
    border: 1px solid #F4C471;
    border-radius: 4px;
    padding: 5px 6px;
}
.server-row-offline {
    background-color: @tt_bg_darkest;
    border: 1px solid @tt_border;
    border-radius: 4px;
    padding: 5px 6px;
}
.server-row-starting {
    background-color: @tt_bg_darkest;
    border: 1px solid @tt_accent;
    border-radius: 4px;
    padding: 5px 6px;
}
.server-model-lbl {
    font-weight: bold;
    font-size: 11px;
}
.server-model-match  { color: #27AE60; }
.server-model-offline { color: @tt_text_muted; }
.server-model-mismatch { color: #F4C471; }
.server-model-starting { color: @tt_accent; }
.server-sub-lbl {
    color: @tt_text_hint;
    font-size: 9px;
}
.server-switch-btn {
    background: transparent;
    border: 1px solid #F4C471;
    color: #F4C471;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 10px;
}
.server-switch-btn:hover {
    background: rgba(244, 196, 113, 0.15);
}

/* ── Advanced accordion ──────────────────────────────────────────────────── */
.adv-hdr-btn {
    background: @tt_bg_darkest;
    border: 1px solid @tt_border;
    border-radius: 4px;
    padding: 5px 8px;
    color: @tt_text_muted;
    font-size: 10px;
}
.adv-hdr-btn:hover {
    background: @tt_bg_dark;
    border-color: @tt_accent;
}
.adv-summary {
    color: @tt_text_muted;
    font-size: 9px;
}
.adv-summary-changed {
    color: @tt_pink;
    font-size: 9px;
}
.adv-body {
    background: @tt_bg_darkest;
    border: 1px solid @tt_border;
    border-top: none;
    border-bottom-left-radius: 4px;
    border-bottom-right-radius: 4px;
    padding: 8px;
}

/* ── Animate inputs box ──────────────────────────────────────────────────── */
.animate-inputs-box {
    border: 1px solid alpha(@tt_accent, 0.5);
    border-radius: 4px;
    padding: 6px 7px;
    background: @tt_bg_dark;
}
.animate-inputs-title {
    color: @tt_accent;
    font-size: 9px;
}
```

- [ ] **Step 3: Smoke-test CSS loads without error**

```bash
cd /home/ttuser/code/tt-local-generator
/usr/bin/python3 main.py &
sleep 3; kill %1 2>/dev/null; echo "CSS smoke test OK"
```

Expected: no GTK CSS parse errors in stderr.

- [ ] **Step 4: Commit**

```bash
cd /home/ttuser/code/tt-local-generator
git add main_window.py
git commit -m "style: add CSS for accordion, animate-inputs-box, server row states"
```

---

## Task 3: Module-level constants and `ControlPanel` state initialization

**Files:**
- Modify: `main_window.py`

Add `_MODEL_TO_SOURCE` and `_MODEL_DISPLAY_SERVER` dicts at module level (before the `ControlPanel` class definition), and add `_running_model` and `_adv_open` to `ControlPanel.__init__()`.

- [ ] **Step 1: Add module-level constants**

In `main_window.py`, find the line just before `class ControlPanel(` and insert:

```python
# Maps server model ID → UI source tab key.
# Used by both ControlPanel.set_server_state() and MainWindow._on_health_result().
_MODEL_TO_SOURCE: dict = {
    "wan2.2-t2v":           "video",
    "mochi-1-preview":      "video",
    "wan2.2-animate-14b":   "animate",
    "flux.1-dev":           "image",
}
_MODEL_DISPLAY_SERVER: dict = {
    "wan2.2-t2v":           "Wan2.2 online",
    "mochi-1-preview":      "Mochi-1 online",
    "wan2.2-animate-14b":   "Animate-14B online",
    "flux.1-dev":           "FLUX online",
}

```

- [ ] **Step 2: Add instance vars to `ControlPanel.__init__()`**

In `ControlPanel.__init__()` (around line 1560), after `self._server_ready = False`, add:

```python
        self._running_model: "str | None" = None  # model ID from /v1/models, or None
        self._adv_open: bool = False               # accordion expanded state
```

- [ ] **Step 3: Verify no syntax errors**

```bash
cd /home/ttuser/code/tt-local-generator
python3 -c "import main_window; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/ttuser/code/tt-local-generator
git add main_window.py
git commit -m "refactor: add module-level model→source maps and ControlPanel state vars"
```

---

## Task 4: Accordion widget in `_build()`

**Files:**
- Modify: `main_window.py` — `ControlPanel._build()`

This task:
1. Increases prompt textarea height from 90px → 110px
2. Moves animate_box to immediately after chips_scroll (before neg prompt)
3. Removes neg prompt, param_grid, and seed_row from the main vertical flow
4. Appends all three to a new `adv_body` Gtk.Box inside a `Gtk.Revealer`
5. Inserts the accordion header button + revealer between animate_box and the server row

- [ ] **Step 1: Increase prompt height**

Find:
```python
        scroll1.set_size_request(-1, 90)
```

Replace with:
```python
        scroll1.set_size_request(-1, 110)
```

- [ ] **Step 2: Connect spinbutton signals for summary updates**

After the existing `_steps_spin` creation (around line 1784), add a signal connection. Find:
```python
        param_grid.attach(self._steps_spin, 1, 0, 1, 1)
```

Do NOT change this line — just note that `_steps_spin` and `_seed_spin` exist and we'll connect signals in Step 4.

- [ ] **Step 3: Store neg prompt section/hint/scroll as instance attributes**

Currently `neg_hint` and `scroll2` are local variables. We need to move them into `adv_body`. Change:

Find:
```python
        # ── Negative prompt ───────────────────────────────────────────────────
        self.append(self._section("Negative Prompt"))
        neg_hint = Gtk.Label(label="Steer away from: blurry, watermark, low quality, distorted")
        neg_hint.set_xalign(0)
        neg_hint.set_ellipsize(Pango.EllipsizeMode.END)
        neg_hint.add_css_class("hint")
        self.append(neg_hint)
        scroll2 = Gtk.ScrolledWindow()
        scroll2.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll2.set_size_request(-1, 52)
        self._neg_view = Gtk.TextView()
        self._neg_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._neg_view.set_tooltip_text(
            "Describe what you do NOT want in the output.\n"
            "Common: blurry, watermark, text overlay, distorted, low quality"
        )
        scroll2.set_child(self._neg_view)
        self.append(scroll2)

        # ── Parameters ────────────────────────────────────────────────────────
        self.append(self._section("Parameters"))
        param_grid = Gtk.Grid()
```

Replace with (create widgets but do NOT append to `self` — will be appended to `adv_body` later):
```python
        # ── Negative prompt (will go in accordion body) ───────────────────────
        _neg_section_lbl = self._section("Negative Prompt")
        neg_hint = Gtk.Label(label="Steer away from: blurry, watermark, low quality, distorted")
        neg_hint.set_xalign(0)
        neg_hint.set_ellipsize(Pango.EllipsizeMode.END)
        neg_hint.add_css_class("hint")
        scroll2 = Gtk.ScrolledWindow()
        scroll2.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll2.set_size_request(-1, 52)
        self._neg_view = Gtk.TextView()
        self._neg_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._neg_view.set_tooltip_text(
            "Describe what you do NOT want in the output.\n"
            "Common: blurry, watermark, text overlay, distorted, low quality"
        )
        scroll2.set_child(self._neg_view)

        # ── Parameters (will go in accordion body) ────────────────────────────
        _param_section_lbl = self._section("Parameters")
        param_grid = Gtk.Grid()
```

- [ ] **Step 4: Remove `self.append(param_grid)` and seed row appends from main flow**

Find and remove:
```python
        self.append(param_grid)

        # ── Seed image ────────────────────────────────────────────────────────
        # Only relevant for Wan2.2 video; hidden when FLUX image source is selected.
        self._seed_img_section = self._section("Seed Image (optional)")
```

Replace with (just re-create seed_img_section — no `self.append` calls yet):
```python
        # ── Seed image (will go in accordion body) ────────────────────────────
        # Only relevant for Wan2.2 video; hidden when FLUX image source is selected.
        self._seed_img_section = self._section("Seed Image (optional)")
```

Then find:
```python
        self.append(self._seed_img_section)
        seed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
```
Replace with:
```python
        seed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
```

And find (the seed_row append at the end of seed section):
```python
        self._seed_row_widget = seed_row
        self.append(seed_row)

        # ── Animate inputs ────────────────────────────────────────────────────
```
Replace with:
```python
        self._seed_row_widget = seed_row

        # ── Animate inputs ────────────────────────────────────────────────────
```

- [ ] **Step 5: Move animate_box and add CSS class**

Find the current animate_box section and its `self.append(self._animate_box)` line near line 1934:
```python
        self.append(self._animate_box)

        # ── Server control ─────────────────────────────────────────────────────
```

Remove that `self.append(self._animate_box)` line. We will append `_animate_box` in the correct position in Step 6.

Also add CSS class to `self._animate_box`. Find:
```python
        self._animate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._animate_box.set_visible(False)

        self._animate_box.append(self._section("Motion Video"))
```

Replace with:
```python
        self._animate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._animate_box.add_css_class("animate-inputs-box")
        self._animate_box.set_visible(False)

        # Title label inside animate box
        _anim_title = Gtk.Label(label="💃 ANIMATE INPUTS")
        _anim_title.set_xalign(0)
        _anim_title.add_css_class("animate-inputs-title")
        self._animate_box.append(_anim_title)

        self._animate_box.append(self._section("Motion Video"))
```

- [ ] **Step 6: Build and wire the accordion**

After all the widget construction (seed_row, animate inputs section), find the line `self.append(self._animate_box)` has been removed, so immediately before:
```python
        # ── Server control ─────────────────────────────────────────────────────
```

Insert the following block that:
1. Appends animate_box right after chips_scroll (in the flow established by its `set_visible(False)`)
2. Builds accordion header + body
3. Appends all advanced widgets into `adv_body`

First, find:
```python
        self.append(self._chips_scroll)

        # ── Negative prompt ───────────────────────────────────────────────────
```

Replace with:
```python
        self.append(self._chips_scroll)

        # Animate inputs — visible only in animate mode, positioned below chips
        self.append(self._animate_box)

        # ── Advanced settings accordion ───────────────────────────────────────
        self._adv_revealer = Gtk.Revealer()
        self._adv_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._adv_revealer.set_transition_duration(150)
        self._adv_revealer.set_reveal_child(False)

        # Header button — full-width toggle
        self._adv_hdr_btn = Gtk.Button()
        self._adv_hdr_btn.add_css_class("adv-hdr-btn")
        self._adv_hdr_btn.connect("clicked", self._on_adv_toggle)
        hdr_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._adv_arrow_lbl = Gtk.Label(label="▸")
        self._adv_arrow_lbl.set_xalign(0)
        hdr_inner.append(self._adv_arrow_lbl)
        hdr_section_lbl = Gtk.Label(label="Advanced settings")
        hdr_section_lbl.set_xalign(0)
        hdr_section_lbl.set_hexpand(True)
        hdr_inner.append(hdr_section_lbl)
        self._adv_summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr_inner.append(self._adv_summary_box)
        self._adv_hdr_btn.set_child(hdr_inner)
        self.append(self._adv_hdr_btn)

        # Accordion body — contains neg prompt, params, seed image
        adv_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        adv_body.add_css_class("adv-body")
        adv_body.append(_neg_section_lbl)
        adv_body.append(neg_hint)
        adv_body.append(scroll2)
        adv_body.append(_param_section_lbl)
        adv_body.append(param_grid)
        adv_body.append(self._seed_img_section)
        adv_body.append(seed_row)
        self._adv_revealer.set_child(adv_body)
        self.append(self._adv_revealer)

        # Connect spinbuttons to update summary when values change
        self._steps_spin.connect("value-changed", lambda _: self._update_adv_summary())
        self._seed_spin.connect("value-changed", lambda _: self._update_adv_summary())

        # ── Negative prompt ───────────────────────────────────────────────────
```

**Wait** — this approach puts the negative prompt block TWICE (once as the removed `self.append` section, and now as `adv_body.append`). We already removed `self.append` calls from neg/params/seed in Steps 3-4. The new code just does `adv_body.append()`. The `# ── Negative prompt ───────────────────────────────────────────────────` comment line no longer heads a block in `self` — the comment is now just floating. After Step 3, the code creates widgets but doesn't append to `self`. So after the accordion code we're inserting, we need to remove the old comment markers. This is all handled by the careful edit in Step 3 — we changed `self.append(self._section(...))` calls to create `_neg_section_lbl` / `_param_section_lbl` variables without appending. So no further cleanup is needed for the comment.

Correction to the insertion: Replace:
```python
        self.append(self._chips_scroll)

        # ── Negative prompt ───────────────────────────────────────────────────
        _neg_section_lbl = self._section("Negative Prompt")
```

with:
```python
        self.append(self._chips_scroll)

        # Animate inputs — visible only in animate mode, positioned below chips
        self.append(self._animate_box)

        # ── Advanced settings accordion ───────────────────────────────────────
        self._adv_revealer = Gtk.Revealer()
        self._adv_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._adv_revealer.set_transition_duration(150)
        self._adv_revealer.set_reveal_child(False)

        # Header button — full-width toggle
        self._adv_hdr_btn = Gtk.Button()
        self._adv_hdr_btn.add_css_class("adv-hdr-btn")
        self._adv_hdr_btn.connect("clicked", self._on_adv_toggle)
        hdr_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._adv_arrow_lbl = Gtk.Label(label="▸")
        self._adv_arrow_lbl.set_xalign(0)
        hdr_inner.append(self._adv_arrow_lbl)
        hdr_section_lbl = Gtk.Label(label="Advanced settings")
        hdr_section_lbl.set_xalign(0)
        hdr_section_lbl.set_hexpand(True)
        hdr_inner.append(hdr_section_lbl)
        self._adv_summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hdr_inner.append(self._adv_summary_box)
        self._adv_hdr_btn.set_child(hdr_inner)
        self.append(self._adv_hdr_btn)

        # Accordion body — contains neg prompt, params, seed image
        adv_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        adv_body.add_css_class("adv-body")

        # ── Negative prompt ───────────────────────────────────────────────────
        _neg_section_lbl = self._section("Negative Prompt")
```

(i.e. we move the body widget construction to be *inside* the `adv_body` construction block).

Actually, let me reconsider the cleanest approach. The spec says to create widgets first, then append them to `adv_body`. Let me describe a cleaner sequence that's easier to implement correctly:

The cleanest execution order is:
1. Create neg prompt widgets (no `self.append`)
2. Create param_grid + spinbuttons (no `self.append`)
3. Create seed section/row (no `self.append`)
4. Create animate_box (no `self.append` — move to `self.append(self._animate_box)` after chips_scroll)
5. After chips_scroll, `self.append(self._animate_box)`
6. Build accordion: header button, revealer, adv_body
7. `adv_body.append()` neg, params, seed widgets in order
8. `self.append(adv_hdr_btn)`, `self.append(adv_revealer)`
9. Connect spinbutton signals for summary
10. Call `_update_adv_summary()` for initial state
11. Proceed to server row and buttons

The edits in Steps 3-5 create the widgets without appending. Step 6 assembles them. This is the correct approach. The actual code edits are sequential and must be done carefully to avoid double-appending.

- [ ] **Step 7: Add `_on_adv_toggle()` and `_update_adv_summary()` methods**

After `_build()` (find `def _set_source(self, source: str) -> None:` and insert before it):

```python
    def _on_adv_toggle(self, _btn) -> None:
        """Toggle the advanced settings accordion open/closed."""
        self._adv_open = not self._adv_open
        self._adv_revealer.set_reveal_child(self._adv_open)
        self._adv_arrow_lbl.set_label("▾" if self._adv_open else "▸")

    def _update_adv_summary(self) -> None:
        """
        Rebuild the accordion header summary labels.
        Shows current steps and seed values; highlights non-defaults in pink.
        Called when steps or seed spinbuttons change, and once at build time.
        """
        steps_val = int(self._steps_spin.get_value())
        seed_val = int(self._seed_spin.get_value())
        steps_default = (steps_val == 20)
        seed_default = (seed_val == -1)

        # Clear existing summary labels
        child = self._adv_summary_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._adv_summary_box.remove(child)
            child = nxt

        # Rebuild with one label per value, styled by default/changed state
        for text, is_default in [
            (f"steps:{steps_val}", steps_default),
            (f"seed:{seed_val if seed_val != -1 else '−1'}", seed_default),
        ]:
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("adv-summary" if is_default else "adv-summary-changed")
            self._adv_summary_box.append(lbl)

```

- [ ] **Step 8: Call `_update_adv_summary()` at end of `_build()`**

Find the line where spinbutton signals are connected (added in Step 6):
```python
        self._steps_spin.connect("value-changed", lambda _: self._update_adv_summary())
        self._seed_spin.connect("value-changed", lambda _: self._update_adv_summary())
```

Add immediately after:
```python
        self._update_adv_summary()
```

- [ ] **Step 9: Smoke-test accordion UI**

```bash
cd /home/ttuser/code/tt-local-generator
/usr/bin/python3 main.py &
```

Verify:
1. App opens without traceback
2. Prompt textarea is visibly taller
3. "Advanced settings" header button is visible below chips
4. Header shows `steps:20` and `seed:−1` in muted style
5. Clicking header → accordion slides open revealing neg prompt, params, seed image
6. Clicking again → accordion closes
7. Changing steps to 28 → header shows `steps:28` in pink

```bash
kill %1 2>/dev/null
```

- [ ] **Step 10: Commit**

```bash
cd /home/ttuser/code/tt-local-generator
git add main_window.py
git commit -m "feat: accordion drawer for advanced settings in ControlPanel"
```

---

## Task 5: Redesigned server status row

**Files:**
- Modify: `main_window.py` — `ControlPanel._build()`, replace the `srv_row` section

Replace the existing server control row (lines ~1936–1965) with the new two-line structured status box.

- [ ] **Step 1: Replace the server row widget construction**

Find and replace this entire block in `_build()`:

```python
        # ── Server control ─────────────────────────────────────────────────────
        # Status row: indicator label + Start + Stop buttons side by side.
        srv_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._server_lbl = Gtk.Label(label="⬤  Checking server…")
        self._server_lbl.set_xalign(0)
        self._server_lbl.set_hexpand(True)
        self._server_lbl.add_css_class("muted")
        srv_row.append(self._server_lbl)

        self._server_start_btn = Gtk.Button(label="▶ Start")
        self._server_start_btn.add_css_class("server-start-btn")
        self._server_start_btn.set_tooltip_text(
            "Start the inference server using the local launch script.\n"
            "Video → start_wan.sh  ·  Animate → start_animate.sh  ·  Image → start_flux.sh"
        )
        self._server_start_btn.set_sensitive(False)  # enabled once health check confirms server is offline
        self._server_start_btn.connect("clicked", self._on_start_server_clicked)
        srv_row.append(self._server_start_btn)

        self._server_stop_btn = Gtk.Button(label="■ Stop")
        self._server_stop_btn.add_css_class("server-stop-btn")
        self._server_stop_btn.set_tooltip_text(
            "Stop the running inference server Docker container.\n"
            "Stops any container using the tt-media-inference-server image."
        )
        self._server_stop_btn.set_sensitive(False)  # enabled once server is confirmed running
        self._server_stop_btn.connect("clicked", self._on_stop_server_clicked)
        srv_row.append(self._server_stop_btn)

        self.append(srv_row)
```

With:

```python
        # ── Server status row ─────────────────────────────────────────────────
        # Two-line status box: dot + model name + sub-label + action buttons.
        self._server_status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._server_status_box.add_css_class("server-row-offline")

        # Left side: indicator dot
        self._server_dot_lbl = Gtk.Label(label="⬤")
        self._server_dot_lbl.add_css_class("server-model-offline")
        self._server_status_box.append(self._server_dot_lbl)

        # Center: two-line text column (model name + sub-label)
        text_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        text_col.set_hexpand(True)
        self._server_model_lbl = Gtk.Label(label="No server")
        self._server_model_lbl.add_css_class("server-model-lbl")
        self._server_model_lbl.add_css_class("server-model-offline")
        self._server_model_lbl.set_xalign(0)
        self._server_sub_lbl = Gtk.Label(label="localhost:8000 unreachable")
        self._server_sub_lbl.add_css_class("server-sub-lbl")
        self._server_sub_lbl.set_xalign(0)
        text_col.append(self._server_model_lbl)
        text_col.append(self._server_sub_lbl)
        self._server_status_box.append(text_col)

        # Right side: action buttons (Start, Stop, Switch tab)
        btn_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._server_start_btn = Gtk.Button(label="▶ Start")
        self._server_start_btn.add_css_class("server-start-btn")
        self._server_start_btn.set_tooltip_text(
            "Start the inference server using the local launch script.\n"
            "Video → start_wan.sh  ·  Animate → start_animate.sh  ·  Image → start_flux.sh"
        )
        self._server_start_btn.set_sensitive(False)
        self._server_start_btn.connect("clicked", self._on_start_server_clicked)
        btn_col.append(self._server_start_btn)

        self._server_stop_btn = Gtk.Button(label="■ Stop")
        self._server_stop_btn.add_css_class("server-stop-btn")
        self._server_stop_btn.set_tooltip_text(
            "Stop the running inference server Docker container.\n"
            "Stops any container using the tt-media-inference-server image."
        )
        self._server_stop_btn.set_sensitive(False)
        self._server_stop_btn.connect("clicked", self._on_stop_server_clicked)
        btn_col.append(self._server_stop_btn)

        self._server_switch_btn = Gtk.Button(label="Switch tab")
        self._server_switch_btn.add_css_class("server-switch-btn")
        self._server_switch_btn.set_visible(False)
        self._server_switch_btn.set_tooltip_text(
            "Switch to the source tab that matches the running server model"
        )
        self._server_switch_btn.connect("clicked", self._on_switch_to_running_model_tab)
        btn_col.append(self._server_switch_btn)

        self._server_status_box.append(btn_col)
        self.append(self._server_status_box)
```

- [ ] **Step 2: Add `_apply_server_row_style()` helper method**

After `set_server_launching()` (around line 2163), insert:

```python
    def _apply_server_row_style(self, state: str) -> None:
        """
        Switch server row and dot label to the given state style.
        state is one of: 'offline', 'match', 'mismatch', 'starting'.
        Removes all server-row-* and server-model-* classes before adding the new one.
        """
        for cls in ("server-row-offline", "server-row-match",
                    "server-row-mismatch", "server-row-starting"):
            self._server_status_box.remove_css_class(cls)
        self._server_status_box.add_css_class(f"server-row-{state}")

        for cls in ("server-model-offline", "server-model-match",
                    "server-model-mismatch", "server-model-starting"):
            self._server_dot_lbl.remove_css_class(cls)
            self._server_model_lbl.remove_css_class(cls)
        self._server_dot_lbl.add_css_class(f"server-model-{state}")
        self._server_model_lbl.add_css_class(f"server-model-{state}")

```

- [ ] **Step 3: Smoke-test server row renders**

```bash
cd /home/ttuser/code/tt-local-generator
/usr/bin/python3 main.py &
sleep 3
```

Verify:
1. Server row shows "No server" with grey dot and subdued border (offline state)
2. Start button is visible, Stop is visible (both present even if one is insensitive)
3. No traceback

```bash
kill %1 2>/dev/null
```

- [ ] **Step 4: Commit**

```bash
cd /home/ttuser/code/tt-local-generator
git add main_window.py
git commit -m "feat: redesign server status row with model name and match/mismatch states"
```

---

## Task 6: `set_server_state()` and `_on_switch_to_running_model_tab()` / `switch_to_source()`

**Files:**
- Modify: `main_window.py` — replace `set_server_ready()` with `set_server_state()`, add switch methods

- [ ] **Step 1: Add `set_server_state()` — replaces `set_server_ready()`**

Find and replace the existing `set_server_ready()` method:

```python
    def set_server_ready(self, ready: bool) -> None:
        self._server_ready = ready
        if ready:
            self._server_lbl.set_label("⬤  Server ready")
            self._server_lbl.remove_css_class("muted")
            self._server_lbl.add_css_class("teal")
            # Collapse the startup log once the server is confirmed up.
            if self._server_launching:
                self.set_server_launching(False)
        else:
            self._server_lbl.set_label("⬤  Server offline")
            self._server_lbl.remove_css_class("teal")
            self._server_lbl.add_css_class("muted")
        # Start button enabled when server is offline and no operation running.
        # Stop button enabled only when server is confirmed running.
        if not self._server_launching:
            self._server_start_btn.set_sensitive(not ready)
            self._server_stop_btn.set_sensitive(ready)
        self._update_btns()
```

With:

```python
    def set_server_state(self, ready: bool, running_model: "str | None") -> None:
        """
        Update all server-related UI from a health check result.

        ready         — True if /tt-liveness returned 200
        running_model — model ID string from /v1/models, or None if unknown/offline
        """
        self._running_model = running_model
        self._server_ready = False  # recalculated below

        if self._server_launching:
            # Launching state is driven by set_server_launching(); don't override it.
            return

        if not ready:
            # Offline
            self._apply_server_row_style("offline")
            self._server_model_lbl.set_label("No server")
            self._server_sub_lbl.set_label("localhost:8000 unreachable")
            self._server_start_btn.set_sensitive(True)
            self._server_stop_btn.set_sensitive(False)
            self._server_switch_btn.set_visible(False)
        else:
            # Server is up — determine match/mismatch
            source_for_model = (
                _MODEL_TO_SOURCE.get(running_model) if running_model else None
            )
            current_source = self._model_source
            mismatch = (
                source_for_model is not None
                and source_for_model != current_source
            )
            display = (
                _MODEL_DISPLAY_SERVER.get(running_model, "Server online")
                if running_model
                else "Server online"
            )

            if mismatch:
                self._apply_server_row_style("mismatch")
                self._server_model_lbl.set_label(display)
                self._server_sub_lbl.set_label(
                    f"{current_source.capitalize()} tab needs a different server"
                )
                self._server_ready = False
                self._server_switch_btn.set_visible(True)
                self._server_start_btn.set_sensitive(False)
                self._server_stop_btn.set_sensitive(True)
            else:
                self._apply_server_row_style("match")
                self._server_model_lbl.set_label(display)
                self._server_sub_lbl.set_label("localhost:8000")
                self._server_ready = True
                self._server_switch_btn.set_visible(False)
                self._server_start_btn.set_sensitive(False)
                self._server_stop_btn.set_sensitive(True)
                # Collapse startup log once server confirmed ready
                if self._server_launching:
                    self.set_server_launching(False)

        self._update_btns()
```

- [ ] **Step 2: Add `_on_switch_to_running_model_tab()` and `switch_to_source()`**

After `_on_stop_server_clicked()` (find `def _on_stop_server_clicked(self, _btn) -> None:`), insert:

```python
    def _on_switch_to_running_model_tab(self, _btn) -> None:
        """Switch the source selector to the tab that matches the running model."""
        source = _MODEL_TO_SOURCE.get(self._running_model) if self._running_model else None
        if source:
            self.switch_to_source(source)

    def switch_to_source(self, source: str) -> None:
        """
        Programmatically activate a source tab.
        Fires _set_source() via the existing toggled signal handler.
        """
        if source == "video":
            self._src_video_btn.set_active(True)
        elif source == "animate":
            self._src_animate_btn.set_active(True)
        elif source == "image":
            self._src_image_btn.set_active(True)

```

- [ ] **Step 3: Update `_set_source()` to re-evaluate server state on tab switch**

In `_set_source()`, find the last line that calls the source-change callback:
```python
        self._on_source_change(source)
```

Insert immediately before it:
```python
        # Re-evaluate match/mismatch for the newly selected tab.
        # Use _server_ready=True if a model is detected (even if previously mismatched).
        if self._running_model is not None or self._server_ready:
            self.set_server_state(
                self._server_ready or (self._running_model is not None),
                self._running_model
            )
```

- [ ] **Step 4: Verify no references to `set_server_ready()` remain**

```bash
cd /home/ttuser/code/tt-local-generator
grep -n "set_server_ready" main_window.py
```

Expected: zero results (the method and all callers are replaced).

- [ ] **Step 5: Run tests**

```bash
cd /home/ttuser/code/tt-local-generator
python3 -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all 21 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/ttuser/code/tt-local-generator
git add main_window.py
git commit -m "feat: replace set_server_ready() with set_server_state() for model awareness"
```

---

## Task 7: Health worker extension and auto tab-switch

**Files:**
- Modify: `main_window.py` — `MainWindow.__init__()`, `_health_loop()`, `_on_health_result()`

- [ ] **Step 1: Add `_auto_tab_switched` flag to `MainWindow.__init__()`**

Find in `MainWindow.__init__()`:
```python
        self._gen_gallery = None
```

Add after it:
```python
        self._auto_tab_switched = False  # True after first model detection auto-switch
```

- [ ] **Step 2: Extend `_health_loop()` to call `detect_running_model()`**

Find:
```python
    def _health_loop(self) -> None:
        """Runs on background thread. Posts UI updates via GLib.idle_add."""
        while not self._health_stop.is_set():
            ready = self._client.health_check()
            # THREADING: must not touch GTK widgets here — post to main thread
            GLib.idle_add(self._on_health_result, ready)
            self._health_stop.wait(10.0)
```

Replace with:
```python
    def _health_loop(self) -> None:
        """Runs on background thread. Posts UI updates via GLib.idle_add."""
        while not self._health_stop.is_set():
            ready = self._client.health_check()
            running_model: "str | None" = None
            if ready:
                running_model = self._client.detect_running_model()
            # THREADING: must not touch GTK widgets here — post to main thread
            GLib.idle_add(self._on_health_result, ready, running_model)
            self._health_stop.wait(10.0)
```

- [ ] **Step 3: Update `_on_health_result()` for model-aware UI and auto tab-switch**

Find:
```python
    def _on_health_result(self, ready: bool) -> bool:
        # Runs on main thread (called by GLib.idle_add).
        self._controls.set_server_ready(ready)
        if ready and not (self._worker_gen and self._worker_gen._running()):
            self._set_status("Server ready — enter a prompt and click Generate")
        return False  # don't repeat (one-shot idle callback)
```

Replace with:
```python
    def _on_health_result(self, ready: bool, running_model: "str | None") -> bool:
        """Runs on main thread (called by GLib.idle_add)."""
        # Auto-switch source tab on first model detection — once only.
        if running_model and not self._auto_tab_switched:
            source = _MODEL_TO_SOURCE.get(running_model)
            if source and source != self._controls.get_model_source():
                self._controls.switch_to_source(source)
            self._auto_tab_switched = True

        self._controls.set_server_state(ready, running_model)

        if ready and not (self._worker_gen and self._worker_gen._running()):
            self._set_status("Server ready — enter a prompt and click Generate")
        return False  # don't repeat (one-shot idle callback)
```

- [ ] **Step 4: Run full test suite**

```bash
cd /home/ttuser/code/tt-local-generator
python3 -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all 21 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/ttuser/code/tt-local-generator
git add main_window.py
git commit -m "feat: health worker detects running model, auto-switches source tab on startup"
```

---

## Task 8: End-to-end smoke test

- [ ] **Step 1: Start app and verify all states**

```bash
cd /home/ttuser/code/tt-local-generator
/usr/bin/python3 main.py &
```

Work through the smoke test checklist:

**Layout:**
- [ ] Prompt textarea is visibly taller (110px)
- [ ] Style chips visible immediately below prompt (no scrolling needed)
- [ ] "Advanced settings ▸" header button below chips, shows `steps:20  seed:−1`
- [ ] No negative prompt / params / seed image visible in main flow

**Accordion:**
- [ ] Click "Advanced settings" → smooth slide-down reveals neg prompt, params, seed image
- [ ] Click again → smooth slide-up collapses
- [ ] Change Steps to 28 → header shows `steps:28` in pink (even when closed)
- [ ] Change Seed to 42 → header shows `seed:42` in pink
- [ ] Reset both to defaults → values return to muted style

**Source-specific accordion content:**
- [ ] Video tab: seed image section visible inside accordion, guidance hidden
- [ ] Image tab: guidance scale visible inside accordion, seed image hidden
- [ ] Animate tab: `💃 Animate Inputs` box appears below chips (not in accordion)

**Server row (with no server running):**
- [ ] Shows "No server" with grey dot, subdued border
- [ ] Sub-label: "localhost:8000 unreachable"
- [ ] Start button enabled, Stop disabled, Switch tab hidden
- [ ] Generate button disabled

**Server row (with correct server running, if available):**
- [ ] Shows model name (e.g. "Wan2.2 online") with green dot, teal-tinted border
- [ ] Generate button enabled
- [ ] Switch tab button hidden

**Mismatch (switch to wrong tab while server runs):**
- [ ] Row turns amber/yellow, "Switch tab" appears
- [ ] Sub-label explains mismatch
- [ ] Generate button disabled
- [ ] Clicking "Switch tab" → correct tab selected, row turns green

```bash
kill %1 2>/dev/null
```

- [ ] **Step 2: Final test run**

```bash
cd /home/ttuser/code/tt-local-generator
python3 -m pytest tests/ -v
```

Expected: all 21 tests pass.

- [ ] **Step 3: Final commit if any last tweaks needed**

```bash
cd /home/ttuser/code/tt-local-generator
git status
# If any uncommitted changes:
git add main_window.py api_client.py
git commit -m "fix: smoke test tweaks for focused prompt panel"
```

---

## Verification checklist (end-to-end)

- [ ] 21 tests still pass (`test_chip_config.py` + `test_model_attribution.py`)
- [ ] App opens without traceback
- [ ] Prompt textarea taller; chips visible without scrolling
- [ ] Accordion closed by default; smooth slide animation
- [ ] Header always shows `steps:N seed:N`; pink = non-default
- [ ] Advanced settings (neg prompt, params, seed image) accessible only via accordion
- [ ] Animate inputs appear below chips when animate tab selected
- [ ] Server offline → grey row, Start enabled, Generate disabled
- [ ] Server online + correct tab → green row, Generate enabled
- [ ] Server online + wrong tab → amber row, Switch tab visible, Generate disabled
- [ ] Clicking Switch tab → source switches, re-evaluates to green row
- [ ] First health check with model detected → auto tab switch (once only, not on subsequent polls)
- [ ] Launching a server → starting state visible; collapses to ready state on success
