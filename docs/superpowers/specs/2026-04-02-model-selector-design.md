# Model Selector + Attribution Design

**Date:** 2026-04-02  
**Status:** Approved

## Context

The app previously assumed a single fixed model per generation category: Wan2.2-T2V for video, FLUX.1-dev for image. Mochi-1 is being brought up as a second video model, and the image category needs to be ready for API-compatible swaps. Two problems this creates:

1. **No model selection UI** — users can't choose which video model to run without restarting manually.
2. **No attribution** — the gallery and history don't record which model generated each output, making it impossible to compare or audit results once multiple models are in use.

Secondary goal: capture richer per-generation metadata (resolution, frame count, inference tokens, server-side cost units) that the server already returns but the app currently discards.

---

## Approach: Category + Model Fields (Option B)

Keep `_model_source` as the **category** (`"video"`, `"animate"`, `"image"`). Add separate `_video_model` / `_image_model` strings for the **specific model** within that category. The category drives gallery routing, worker selection, and UI shape; the model drives which script launches and what gets recorded.

This avoids rewriting every existing `model_source == "video"` callsite and keeps the three-tab structure intact. Animate tab is unchanged.

---

## File-by-File Changes

### `history_store.py`

**`GenerationRecord`** gets two new fields:

```python
model: str = ""          # e.g. "wan2.2-t2v", "mochi-1-preview", "flux.1-dev"
extra_meta: dict = field(default_factory=dict)
                         # free-form server response metadata:
                         # resolution, frame_count, tokens, cost_units, etc.
```

- `GenerationRecord.new()` and `new_image()` gain a `model: str = ""` parameter.
- JSON deserialisation: missing `model` → `""` (legacy records silently downgrade; display treats `""` as "unknown").
- `extra_meta` serialises as a nested JSON object; missing key → `{}`.

### `api_client.py`

**`poll_status()`** currently discards everything except `status` and `error`. Change signature:

```python
def poll_status(self, job_id: str) -> Tuple[str, Optional[str], dict]:
    # returns (status, error, full_response_dict)
```

The third element is `data` from the server's JSON response — callers that don't need it can ignore it. Zero extra HTTP calls; we capture what's already coming back.

No other changes to `api_client.py`. Mochi-1 uses the same endpoints as Wan2.2 (`/v1/videos/generations`), so no new methods are needed.

### `worker.py`

**`GenerationWorker`**:
- Constructor gains `model: str = "wan2.2-t2v"`.
- Poll loop: when `status == "completed"`, stash the full response dict.
- Pass `model=self._model` and `extra_meta=<response_dict>` to `GenerationRecord.new()`.

**`ImageGenerationWorker`**:
- Constructor gains `model: str = "flux.1-dev"`.
- Pass `model` to `GenerationRecord.new_image()`.
- Image API is synchronous (no poll loop), so `extra_meta` comes from the single POST response body minus the `images` field (which would be enormous; strip it before storing).

`AnimateGenerationWorker`: unchanged.

### `main_window.py` — `ControlPanel`

**New state:**
```python
self._video_model: str = "wan2"   # "wan2" | "mochi"
self._image_model: str = "flux"   # "flux" | ...
```

**New accessors:**
```python
def get_video_model(self) -> str: ...
def get_image_model(self) -> str: ...
```

**New model selector row** (built in `_build()`):

Sits immediately below the source toggle buttons, above `_source_desc_lbl`. Uses the same `source-btn` / `source-btn-active` CSS classes for visual consistency:

```
[ 🎬 Wan2.2 ][ 🎥 Mochi-1 ]     ← visible when source == "video"
[ 🖼 FLUX ]                       ← visible when source == "image" (single btn, no toggle needed until 2nd model added)
                                   ← hidden when source == "animate"
```

- `_model_selector_row` is a `Gtk.Box`; visibility toggled by `_set_source()`.
- `_set_model(model: str)` updates active/inactive CSS, updates `_source_desc_lbl`, and updates the Start button tooltip.

**`_source_desc_lbl` values:**

| Source | Model | Text |
|--------|-------|------|
| video | wan2 | `async job · Wan2.2-T2V · ~3–10 min · 720p MP4` |
| video | mochi | `async job · Mochi-1 · ~5–15 min · 480×848 168-frame` |
| image | flux | `synchronous · FLUX.1-dev · ~15–90 s · 1024×1024 JPEG` |
| animate | — | `async job · Animate-14B · motion video + character` |

**`_on_start_server_clicked()`**: unchanged — still calls `self._on_start_server(self._model_source)`. `MainWindow` reads the model from `self._controls.get_video_model()`.

**`_on_generate` / `_on_enqueue` args**: the `model_source` arg already flows through. No signature change needed — `MainWindow._on_generate()` reads the model from `self._controls` at call time.

### `main_window.py` — `MainWindow`

**`_on_start_server(model_source)`**: replace the three-branch if/elif with a clean lookup:

```python
video_model = self._controls.get_video_model()
image_model = self._controls.get_image_model()

_SCRIPTS = {
    ("video",   "wan2"):  ("start_wan.sh",     "Wan2.2 video"),
    ("video",   "mochi"): ("start_mochi.sh",   "Mochi-1 video"),
    ("image",   "flux"):  ("start_flux.sh",    "FLUX image"),
    ("animate", ""):      ("start_animate.sh", "Wan2.2-Animate"),
}
model_key = video_model if model_source == "video" else image_model if model_source == "image" else ""
script_name, label = _SCRIPTS.get((model_source, model_key), ("start_wan.sh", "video"))
```

**`_on_generate()` signature change**: add `model_id: str = ""` parameter after `model_source`. This is needed so queued items carry the model that was selected *at enqueue time*, not the current selection:

```python
def _on_generate(self, prompt, neg, steps, seed, seed_image_path="",
                 model_source="video", guidance_scale=3.5,
                 ref_video_path="", ref_char_path="",
                 animate_mode="animation", model_id="") -> None:
```

**`ControlPanel._on_action_clicked()`**: include `model_id` in the args tuple:

```python
args = (
    prompt, neg, steps, seed, seed_image_path,
    self._model_source,
    float(self._guidance_spin.get_value()),
    self._ref_video_path, self._ref_char_path, self._animate_mode,
    self._video_model if self._model_source == "video" else self._image_model,
)
```

**`_QueueItem`**: `model_id` field is already specified below — `_start_next_queued` passes `item.model_id` as the final arg when calling `_on_generate`.

**`_on_generate()`**: pass `model` to the worker constructors:

```python
# video branch:
model_id = {"wan2": "wan2.2-t2v", "mochi": "mochi-1-preview"}.get(
    self._controls.get_video_model(), "wan2.2-t2v")
gen = GenerationWorker(..., model=model_id)

# image branch:
model_id = {"flux": "flux.1-dev"}.get(self._controls.get_image_model(), "flux.1-dev")
gen = ImageGenerationWorker(..., model=model_id)
```

**`_load_history()`**: all video records (regardless of `model`) go to `_video_gallery`. No change needed here; the gallery itself already shows all non-image records.

### `main_window.py` — `GenerationCard` (attribution badges)

The card currently shows a `VIDEO` or `IMAGE` type badge. Add a **model badge** immediately below it when `record.model` is non-empty:

```
[ VIDEO ]
[ Wan2.2 ]    ← new, using .type-badge-model CSS class
```

Model display names:
```python
_MODEL_DISPLAY = {
    "wan2.2-t2v":       "Wan2.2",
    "mochi-1-preview":  "Mochi-1",
    "flux.1-dev":       "FLUX",
    "":                 "",   # legacy — badge omitted
}
```

New CSS class `.type-badge-model` — muted style, less prominent than the type badge:
```css
.type-badge-model {
    background-color: #0F2A35;
    color: #607D8B;
    border: 1px solid #2D5566;
    border-radius: 3px;
    padding: 0px 4px;
    font-size: 10px;
}
```

### `main_window.py` — `DetailPanel`

In the metadata section, add:
- `Model:` row showing `record.model` (or `"unknown"` if empty) — shown for all records
- Expand extra_meta display: iterate `record.extra_meta` and render any keys the server returns. Interesting keys to surface if present: `resolution`, `frame_count`, `tokens_used`, `cost_units`, `output_fps`.

Keys that are already shown via dedicated fields (prompt, steps, seed, duration) are skipped in extra_meta rendering to avoid duplication.

---

## `_QueueItem` changes

Add `model_id: str = ""` field so queued items remember which specific model was selected at enqueue time (not at dequeue time, which could be after the user switches models).

---

## Backward Compatibility

- Existing history JSON loads without `model` → `""` → no badge shown, "unknown" in detail panel. No data loss.
- `poll_status()` callers that unpack `(status, error)` will need to be updated to `(status, error, _)` or `(status, error, meta)`. Only `GenerationWorker` calls this.

---

## What's Explicitly Out of Scope

- Animate tab model selection (deferred until model is working)
- FLUX img2img / seed image support
- Cloud cost estimation (placeholder only — `cost_units` stored if server returns it, but no pricing formula applied)
- Separate per-model galleries (all video in one gallery; model badge provides attribution)

---

## Verification

1. Launch app: `python3 main.py`
2. Video tab → model selector shows `[ Wan2.2 ][ Mochi-1 ]`
3. Switch to Mochi-1 → description line updates, Start tooltip says `start_mochi.sh`
4. Switch to Image tab → model selector shows `[ FLUX ]` (single button, no toggle)
5. Switch to Animate tab → no model selector visible
6. Generate a video with Wan2.2 → gallery card shows `VIDEO` + `Wan2.2` badges
7. Check detail panel → `Model: wan2.2-t2v`, `extra_meta` keys rendered if server returned them
8. Check history JSON (`~/.local/share/tt-video-gen/history.json`) → record has `"model": "wan2.2-t2v"` field
9. Restart app → legacy records (no `model` field) load without error, no model badge shown
10. Start server with Mochi-1 selected → `start_mochi.sh --gui` is invoked
