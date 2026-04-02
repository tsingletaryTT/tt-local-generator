# Focused Prompt Panel Design

**Date:** 2026-04-02
**Status:** Approved

---

## Context

The left `ControlPanel` stacks every option vertically: prompt, chips, negative prompt, parameters, seed image, animate inputs, and server controls. To reach Generate the user must scroll past sections they rarely change. There is no visual hierarchy separating "things I touch every generation" from "things I touch occasionally." The server status row says "Server ready" with no indication of which model is running, making it impossible to know at a glance whether the running server matches what the selected tab needs.

---

## Goals

1. **Focused prompt experience** — prompt textarea + style chips dominate the visible panel; everything else is behind one click.
2. **Advanced settings accordion** — negative prompt, steps, seed, guidance scale, seed image collapse into a `Gtk.Revealer`-based drawer whose header always shows current values; non-default values are highlighted pink so the user knows at a glance what they've tuned.
3. **Server model awareness** — the health worker detects which model is running; the server row reflects `match`, `mismatch`, `offline`, or `starting` state; the panel auto-selects the correct source tab on first detection.

---

## File Map

| File | Action |
|------|--------|
| `api_client.py` | Add `detect_running_model() -> str \| None` |
| `main_window.py` | Overhaul `ControlPanel._build()`, refactor `set_server_ready()` → `set_server_state()`, update `_health_loop()` + `_on_health_result()`, add CSS |

---

## `api_client.py` — `detect_running_model()`

New method on `APIClient`:

```python
def detect_running_model(self) -> str | None:
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

---

## `main_window.py` — `ControlPanel` changes

### CSS additions

Add to `_CSS`:

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

### `_build()` restructuring

**Prompt textarea height:** Change `set_size_request(-1, 90)` → `set_size_request(-1, 110)`.

**Remove from main flow (moved into accordion):**
- `self._section("Negative Prompt")` label + hint + scroll2
- `self._section("Parameters")` label + `param_grid`
- `self._section("Seed Image (optional)")` label + seed_row

These widgets are still created (same attribute names, same logic), but appended to the accordion body instead of directly to `self`.

**Animate inputs position:** `self._animate_box` appended immediately after `self._chips_scroll` — before the accordion. Currently it's appended after seed_row; move it.

**Accordion widget (new):**

```python
# ── Advanced settings accordion ───────────────────────────────────────────
self._adv_open = False
self._adv_revealer = Gtk.Revealer()
self._adv_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
self._adv_revealer.set_transition_duration(150)

# Header button — full-width, shows summary
self._adv_hdr_btn = Gtk.Button()
self._adv_hdr_btn.add_css_class("adv-hdr-btn")
self._adv_hdr_btn.connect("clicked", self._on_adv_toggle)
hdr_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
self._adv_arrow_lbl = Gtk.Label(label="▸")
self._adv_arrow_lbl.set_xalign(0)
hdr_inner.append(self._adv_arrow_lbl)
hdr_lbl = Gtk.Label(label="Advanced settings")
hdr_lbl.set_xalign(0)
hdr_lbl.set_hexpand(True)
hdr_inner.append(hdr_lbl)
self._adv_summary_lbl = Gtk.Label(label="")
self._adv_summary_lbl.set_xalign(1)
hdr_inner.append(self._adv_summary_lbl)
self._adv_hdr_btn.set_child(hdr_inner)
self.append(self._adv_hdr_btn)

# Body — wrapped in Revealer
adv_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
adv_body.add_css_class("adv-body")
# ... append neg prompt, param_grid, seed_row to adv_body
self._adv_revealer.set_child(adv_body)
self.append(self._adv_revealer)

self._update_adv_summary()
```

**`_on_adv_toggle()`:**

```python
def _on_adv_toggle(self, _btn) -> None:
    self._adv_open = not self._adv_open
    self._adv_revealer.set_reveal_child(self._adv_open)
    self._adv_arrow_lbl.set_label("▾" if self._adv_open else "▸")
```

**`_update_adv_summary()`:**

Generates the summary string shown in the accordion header. Always displays steps and seed. Marks non-default values with `.adv-summary-changed` CSS class by using Pango markup or by toggling a CSS class on the label.

Implementation: render as a single label using two CSS spans is not trivially supported without Pango markup. Instead use a `Gtk.Box` with two `Gtk.Label` children — one for steps, one for seed — each independently styled.

```python
def _update_adv_summary(self) -> None:
    """Rebuild the accordion header summary labels. Called when steps or seed changes."""
    steps_val = int(self._steps_spin.get_value())
    seed_val = int(self._seed_spin.get_value())
    steps_default = (steps_val == 20)
    seed_default = (seed_val == -1)

    steps_text = f"steps:{steps_val}"
    seed_text = f"seed:{seed_val if seed_val != -1 else '−1'}"

    # Rebuild the summary box (two labels)
    # Clear existing children
    child = self._adv_summary_box.get_first_child()
    while child:
        nxt = child.get_next_sibling()
        self._adv_summary_box.remove(child)
        child = nxt

    for text, is_default in [(steps_text, steps_default), (seed_text, seed_default)]:
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("adv-summary" if is_default else "adv-summary-changed")
        self._adv_summary_box.append(lbl)
```

`self._adv_summary_box` is a `Gtk.Box(HORIZONTAL, spacing=6)` placed where `self._adv_summary_lbl` was in the header.

Connect to spinbutton signals after creation:
```python
self._steps_spin.connect("value-changed", lambda _: self._update_adv_summary())
self._seed_spin.connect("value-changed", lambda _: self._update_adv_summary())
```

### Server row redesign

Replace the existing `srv_row` (Label + Start + Stop) with a two-row structured box.

New structure inside `ControlPanel._build()`:

```python
# ── Server status row ─────────────────────────────────────────────────────
self._server_status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
self._server_status_box.add_css_class("server-row-offline")

# Left: dot + text column
self._server_dot_lbl = Gtk.Label(label="⬤")
self._server_dot_lbl.add_css_class("server-model-offline")
self._server_status_box.append(self._server_dot_lbl)

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

# Right: action buttons column (Start, Stop, Switch tab)
btn_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
self._server_start_btn = Gtk.Button(label="▶ Start")
self._server_start_btn.add_css_class("server-start-btn")
self._server_start_btn.set_sensitive(False)
self._server_start_btn.connect("clicked", self._on_start_server_clicked)
btn_col.append(self._server_start_btn)

self._server_stop_btn = Gtk.Button(label="■ Stop")
self._server_stop_btn.add_css_class("server-stop-btn")
self._server_stop_btn.set_sensitive(False)
self._server_stop_btn.connect("clicked", self._on_stop_server_clicked)
btn_col.append(self._server_stop_btn)

self._server_switch_btn = Gtk.Button(label="Switch tab")
self._server_switch_btn.add_css_class("server-switch-btn")
self._server_switch_btn.set_visible(False)
self._server_switch_btn.connect("clicked", self._on_switch_to_running_model_tab)
btn_col.append(self._server_switch_btn)

self._server_status_box.append(btn_col)
self.append(self._server_status_box)
```

### `set_server_state(ready, running_model)` — replaces `set_server_ready()`

```python
# ── Server state constants ─────────────────────────────────────────────────
# Maps model ID → source tab key. Used for mismatch detection and tab switching.
_MODEL_TO_SOURCE = {
    "wan2.2-t2v":           "video",
    "mochi-1-preview":      "video",
    "wan2.2-animate-14b":   "animate",
    "flux.1-dev":           "image",
}
_MODEL_DISPLAY_SERVER = {
    "wan2.2-t2v":           "Wan2.2 online",
    "mochi-1-preview":      "Mochi-1 online",
    "wan2.2-animate-14b":   "Animate-14B online",
    "flux.1-dev":           "FLUX online",
}
```

```python
def set_server_state(self, ready: bool, running_model: str | None) -> None:
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
        source_for_model = _MODEL_TO_SOURCE.get(running_model, None) if running_model else None
        current_source = self._model_source
        mismatch = (source_for_model is not None and source_for_model != current_source)

        display = _MODEL_DISPLAY_SERVER.get(running_model, "Server online") if running_model else "Server online"

        if mismatch:
            self._apply_server_row_style("mismatch")
            self._server_model_lbl.set_label(display)
            needed = current_source.capitalize()
            self._server_sub_lbl.set_label(f"{needed} tab needs a different server")
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
            # Collapse startup log if it was open
            if self._server_launching:
                self.set_server_launching(False)

    self._update_btns()
```

`_apply_server_row_style(state: str)` removes all `server-row-*` CSS classes and adds the correct one, does the same for the dot label's `server-model-*` class.

### `_on_switch_to_running_model_tab()`

```python
def _on_switch_to_running_model_tab(self, _btn) -> None:
    source = _MODEL_TO_SOURCE.get(self._running_model)
    if source:
        # Activate the correct source ToggleButton — this fires _set_source() via toggled signal
        if source == "video":
            self._src_video_btn.set_active(True)
        elif source == "animate":
            self._src_animate_btn.set_active(True)
        elif source == "image":
            self._src_image_btn.set_active(True)
```

### `_set_source()` update

After a source switch (whether user-initiated or via switch button), call `set_server_state()` with the cached `self._running_model` to re-evaluate match/mismatch for the new tab:

```python
# At end of _set_source(), after all visibility updates:
self.set_server_state(self._server_ready or (self._running_model is not None), self._running_model)
```

---

## `main_window.py` — `MainWindow` health worker changes

### `_health_loop()` — extend to detect model

```python
def _health_loop(self) -> None:
    """Runs on background thread. Posts UI updates via GLib.idle_add."""
    while not self._health_stop.is_set():
        ready = self._client.health_check()
        running_model: str | None = None
        if ready:
            running_model = self._client.detect_running_model()
        GLib.idle_add(self._on_health_result, ready, running_model)
        self._health_stop.wait(10.0)
```

### `_on_health_result()` — auto tab switch on first detection

```python
def _on_health_result(self, ready: bool, running_model: str | None) -> bool:
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
    return False
```

Add `self._auto_tab_switched = False` to `MainWindow.__init__()`.

`switch_to_source(source: str)` is a new thin method on `ControlPanel` that activates the right toggle button programmatically.

---

## Module-level constants

`_MODEL_TO_SOURCE` and `_MODEL_DISPLAY_SERVER` are defined at **module level** in `main_window.py` (not inside `ControlPanel`), so both `ControlPanel.set_server_state()` and `MainWindow._on_health_result()` can reference them without cross-class attribute access.

## `ControlPanel.switch_to_source(source: str)`

New thin method — activates the correct source toggle button programmatically, triggering the existing `toggled` signal handler and all downstream `_set_source()` logic:

```python
def switch_to_source(self, source: str) -> None:
    """Programmatically activate a source tab. Fires _set_source() via toggled signal."""
    if source == "video":
        self._src_video_btn.set_active(True)
    elif source == "animate":
        self._src_animate_btn.set_active(True)
    elif source == "image":
        self._src_image_btn.set_active(True)
```

Used by `MainWindow._on_health_result()` for auto tab-switch and by `_on_switch_to_running_model_tab()` — consolidates the logic in one place, removing duplication.

---

## Existing `set_server_ready()` callers

`set_server_ready(bool)` is called in one place other than the health result: `set_server_launching()` calls `_update_btns()` indirectly. The launching state check inside `set_server_state()` short-circuits so `set_server_launching()` remains unchanged. Remove the old `set_server_ready()` method after updating `_on_health_result()`.

---

## Accordion body contents (layout order)

Inside `adv_body` (Gtk.Box VERTICAL):

1. `_section("Negative Prompt")` label (section-label style)
2. Negative prompt hint label
3. `scroll2` (negative prompt ScrolledWindow + TextView) — unchanged
4. `_section("Parameters")` label
5. `param_grid` (steps + seed + guidance) — unchanged
6. `_section("Seed Image (optional)")` label — only visible when source == "video"
7. `seed_row` — only visible when source == "video"

The visibility logic for `_guidance_lbl`, `_guidance_spin`, `_guidance_hint_lbl` (shown only for image source) and `_seed_img_section`, `_seed_row_widget` (shown only for video source) is unchanged; it still runs inside `_set_source()`.

---

## Animate inputs position

`self._animate_box` is currently appended at the end of `_build()` before the server row. In the new layout it is appended immediately after `self._chips_scroll`:

```
chips_scroll → animate_box (hidden unless animate) → adv_hdr_btn → adv_revealer → spacer → server_status_box → gen_btn → cancel_btn → recover_btn
```

Add `.animate-inputs-box` CSS class to `self._animate_box` and add `self._section("💃 Animate inputs")` as the first child of that box.

---

## Summary of what moves where

| Element | Was | Now |
|---------|-----|-----|
| Negative prompt | Directly in panel | Accordion body |
| Steps spinbutton | Directly in panel | Accordion body |
| Seed spinbutton | Directly in panel | Accordion body |
| Guidance scale | Directly in panel | Accordion body |
| Seed image | Directly in panel | Accordion body |
| Animate inputs box | After seed image section | After chips, before accordion |
| Server row | 1 label + Start + Stop | 2-line status box + Stop + Start + Switch tab |
| Prompt height | 90 px | 110 px |

---

## What is NOT changing

- `ControlPanel.get_prompt()`, `get_negative_prompt()`, `get_steps()`, `get_seed()`, `get_guidance_scale()`, `get_seed_image_path()` — same methods, same widget reads
- `_on_action_clicked()` — unchanged
- `ControlPanel` constructor signature — no new parameters
- All chip logic — unchanged
- `set_server_launching()` and server log panel — unchanged
- `set_busy()` — unchanged
- Queue display — unchanged (already moved to below detail panel)

---

## Testing

All changes are GTK UI — no new non-GTK logic, so no new unit tests are required. The existing 21 tests (`test_chip_config.py` + `test_model_attribution.py`) must still pass. Verification is by smoke-testing the running app.

Smoke test checklist:
- [ ] App opens without traceback
- [ ] Accordion closed by default; clicking header reveals body with smooth slide
- [ ] Accordion header shows `steps:20  seed:−1` in muted color by default
- [ ] Changing steps to 28: header shows `steps:28` in pink
- [ ] Changing seed to any non-−1 value: header shows that seed in pink
- [ ] Video mode: seed image visible inside accordion; guidance scale hidden
- [ ] Image mode: guidance scale visible inside accordion; seed image hidden
- [ ] Animate mode: animate inputs box appears below chips
- [ ] Switching to Animate collapses animate-irrelevant accordion items correctly
- [ ] Server offline: grey row, "No server", Start enabled, Generate disabled
- [ ] Server online (correct tab): green-tinted row, model name, Stop enabled, Generate enabled
- [ ] Server online (wrong tab): amber row, "Switch tab" button, Generate disabled
- [ ] Clicking "Switch tab": switches to correct source, row turns green
- [ ] Auto tab switch: on startup with running server, correct tab pre-selected (once only)
- [ ] Starting a server: teal row "Starting Wan2.2…", log visible, row turns green when ready
