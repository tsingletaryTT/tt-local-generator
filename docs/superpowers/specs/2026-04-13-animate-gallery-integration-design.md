# Animate Gallery Integration Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the gallery a first-class input source for Animate, so generated videos and images become motion references and character seeds — embodying the Create → Curate → Watch flow.

**Architecture:** Three interlocking pieces: (1) gallery cards gain slide-up hover actions that pre-fill animate inputs; (2) the animate panel's Browse-button file pickers are replaced with compact thumbnail widgets that open a three-tab popover picker (Bundled / Gallery / Disk); (3) the mode toggle gains an inline description bar on hover explaining each mode's effect.

**Tech Stack:** GTK4/Python, existing GalleryWidget/GenerationCard/HistoryStore patterns, Gtk.Popover, ffmpeg thumbnail extraction (already in use), app/assets/motion_clips/ directory of bundled MP4s.

---

## 1. Gallery Card Hover Actions

### What changes
Every `GenerationCard` in the Video and Animate galleries gains a slide-up action bar on hover. The bar uses a gradient overlay (transparent → `rgba(15,42,53,0.92)`) rising from the bottom of the card, with two labeled buttons.

### Button behaviour by card type

| Card type | Buttons shown | Action |
|-----------|---------------|--------|
| Video output | 💃 Animate (teal) + ↗ Motion (pink) | See below |
| Animate output | 💃 Animate (teal) + ↗ Motion (pink) | See below |
| Image output | 💃 Animate (teal) only | See below |

**💃 Animate** — switches the source selector to "animate" if not already there, copies the card's `thumbnail_path` into the Character Image input (thumbnail is a JPEG first-frame for videos, the image itself for image outputs), shows a brief status flash "Character set ✓" in the panel.

**↗ Motion** — sets the card's `video_path` as the Motion Video input without changing the source selector, shows "Motion set ✓". Only shown on video/animate cards.

Both actions update the corresponding `InputWidget` (see §2) and do not trigger generation — the user still presses Animate.

### Implementation notes
- Add `_on_animate_action(record)` and `_on_motion_action(record)` signal callbacks on `GenerationCard`, connected via lambdas at card construction time in `GalleryWidget`.
- The action bar is a `Gtk.Revealer` (transition: `SLIDE_UP`, 150 ms) containing a `Gtk.Box` with two `Gtk.Button` children. The revealer is added as an overlay child in the existing `Gtk.Overlay` on each card.
- Hover detection: connect `Gtk.EventControllerMotion` `enter` / `leave` signals on the card frame.
- The "status flash" is a 1.5 s timeout on the existing panel status label (already used for "Submitting…" messages).

---

## 2. Animate Input Widgets (`InputWidget`)

### What changes
The current animate panel layout:
```
Motion Video:    [---- none ----]  [Browse…]
Character Image: [---- none ----]  [Browse…]
```
is replaced with two side-by-side `InputWidget` instances inside a single `Gtk.Box(orientation=HORIZONTAL, spacing=6)`.

### InputWidget appearance
Each widget is a `Gtk.Button` subclass with a vertical layout:
- **Type label** — muted uppercase 8 px ("MOTION VIDEO" / "CHARACTER")
- **Thumbnail area** — 100% width, 40 px tall; shows first-frame of selected video or the image; shows a `+` placeholder when empty
- **Name row** — truncated filename left, `▾` caret right, 8 px

Border styling (via CSS class toggling):
- `.input-widget` — base style, muted border
- `.input-widget-filled-motion` — pink `#ec96b8` border (1 px)
- `.input-widget-filled-char` — teal `#4fd1c5` border (1 px)

Clicking anywhere on the widget opens its popover (§3).

### State held by the panel
`self._ref_video_path: str` and `self._ref_char_path: str` — already exist. The `InputWidget` is given a `set_value(path)` method that updates the thumbnail and name label, and adds/removes the filled CSS class. The gallery card actions and the popover picker both call `set_value`.

---

## 3. Three-Tab Popover Picker

A `Gtk.Popover` (`.popover-picker` CSS class) anchored to the clicked `InputWidget`. Width 300 px, max height 360 px with a scrolled interior.

### Shared structure
```
┌─────────────────────────────────┐
│ Pick Motion Video             ✕ │  ← title + close button
├──────────────────────────────── │
│ 📦 Bundled │ 🎬 Gallery │ 📁 Disk│  ← tab bar
├──────────────────────────────── │
│  [tab content — scrollable]     │
├──────────────────────────────── │
│               [Cancel] [Use this]│  ← footer
└─────────────────────────────────┘
```

The popover title changes: "Pick Motion Video" or "Pick Character Image".

Internally the tab bar is a `Gtk.Stack` + three `Gtk.ToggleButton` tabs (same `.source-btn` pattern as the top toolbar). Selected thumbnail stored in `_picker_selection: str | None`; "Use this" is insensitive when `None`.

### 📦 Bundled tab
Scans `app/assets/motion_clips/` at popover open. Top row: category filter chips derived from subdirectory names. Clicking a chip filters the grid below. Grid: `Gtk.FlowBox`, each cell is a 64×46 px thumbnail with filename label. Thumbnails are extracted once on first scan and cached alongside each clip as `<name>.jpg` (same ffmpeg path as gallery thumbnails). The Character picker **omits** the Bundled tab entirely (users supply their own character).

### 🎬 Gallery tab
Reads `HistoryStore` directly (already in memory). For the **Motion** picker: only `media_type == "video"` records, newest first, using `thumbnail_path`. For the **Character** picker: all records, using `thumbnail_path` (video thumbnails are first-frame stills — valid character seeds). Grid uses same 64×46 cells. Empty state: "No generated outputs yet."

### 📁 Disk tab
Top: folder path row — shows `motion_clips_dir` from settings with a "Change…" `Gtk.Button` (opens `Gtk.FileDialog` in folder mode; saves to settings on confirm). Below: grid of video/image files found in the folder, thumbnails extracted on first open and cached in `~/.cache/tt-video-gen/disk_thumbs/`. Dashed "Browse…" tile at end opens a single-file `Gtk.FileDialog` for one-off picks. Empty folder state: "No files in folder — drag some in or click Browse."

### Thumbnail extraction helper
`extract_thumbnail(src_path: str, dest_path: str) -> bool` — thin wrapper around the existing ffmpeg call already used in `GenerationWorker._extract_thumbnail`. Reuse as-is.

---

## 4. Mode Toggle — Inline Description Bar

### What changes
The existing `Gtk.Box` holding the Animation / Replacement toggle buttons gains a `Gtk.Revealer` (transition: `SLIDE_DOWN`, 120 ms) directly below it, with no gap between them so they read as a single connected widget.

The revealer contains a `Gtk.Box` (`.mode-desc-bar`) with:
- Icon label (💃 or 🔀, 18 px)
- Description text (9 px, wrapping)
- Impact line (8 px, coloured to match the hovered mode)

CSS: `.mode-desc-bar-anim` uses teal accent colours; `.mode-desc-bar-repl` uses pink.

### Copy

**Animation** (teal):
> Your character performs the motion from the reference video. Their appearance is preserved; only the movement is transferred.
> ↳ Reference video sets the motion · Character appearance comes from your image

**Replacement** (pink):
> Your character replaces the person in the reference video. Motion, background, and timing come from the reference.
> ↳ Needs a visible person in the reference video · Background is preserved

### Hover wiring
`Gtk.EventControllerMotion` on each mode button. `enter` → set bar content + CSS class + reveal. `leave` → un-reveal after 200 ms delay (prevents flicker when moving between the two buttons).

---

## 5. Bundled Clips Library

### Directory structure
```
app/assets/motion_clips/
  walk/
    walk_forward.mp4      3–4 s, 480×832, plain background
    walk_backward.mp4
    walk_strut.mp4
  run/
    run_forward.mp4
  dance/
    dance_basic.mp4
    dance_spin.mp4
  turn/
    turn_left_90.mp4
    turn_right_90.mp4
    turn_180.mp4
  wave/
    wave_hello.mp4
    wave_big.mp4
  jump/
    jump_basic.mp4
  gestures/
    live_long_and_prosper.mp4
    hang_loose.mp4
    hang_in_there.mp4
```

Categories are read from subdirectory names at runtime — adding a new category requires no code change.

### Sourcing
**Locomotion clips** (walk / run / dance / turn / wave / jump): sourced from [Mixamo](https://mixamo.com) — free Adobe account required. Steps: pick animation → apply to Y-Bot neutral character → download FBX → import to Blender → render 480×832 MP4 with plain `#1a3c47` background, 24 fps, ~3–5 s. The plain dark background maximises motion signal clarity for the Animate model.

**Gesture clips** (gestures/): generated using the app's own Wan2.2 T2V model. Suggested prompts (480×832, 25 steps, plain background):

| Clip | Prompt |
|------|--------|
| `live_long_and_prosper.mp4` | `a person slowly raises their right hand and holds up the Vulcan salute, fingers split in a V shape, plain dark background, cinematic` |
| `hang_loose.mp4` | `a person extends their arm outward and holds the shaka sign, thumb and pinky out, relaxed smile, plain dark background` |
| `hang_in_there.mp4` | `a person grips a horizontal bar with both hands and hangs, feet dangling, determined expression, slight swinging motion, plain dark background` |

Prompts and generation parameters are stored alongside each clip as `<name>.txt` so they can be regenerated or extended later.

---

## 6. Settings: Disk Folder Persistence

New key in `~/.local/share/tt-video-gen/settings.json`:
```json
{ "motion_clips_dir": "" }
```
Default empty string → Disk tab shows only the "Browse…" tile. `SettingsStore` (or equivalent) gains `get_motion_clips_dir() -> str` and `set_motion_clips_dir(path: str)` methods. The folder is scanned on each popover open (not watched continuously — typical folder sizes make this fast enough).

---

## 7. Error Handling

- **Thumbnail extraction fails** (corrupt file, ffmpeg not found): show a grey placeholder with a `?` icon; do not crash the popover.
- **Bundled clips directory missing**: Bundled tab shows "No bundled clips found." No exception.
- **Gallery record video_path not on disk**: skip that record silently (file may have been manually deleted).
- **Disk folder unreadable**: show "Cannot read folder — check permissions." with a "Change…" button.
- **Card action while server is busy**: the inputs update immediately (instant local state change); the user may still need to wait for the current job before submitting.

---

## 8. Testing

- Unit: `InputWidget.set_value` updates thumbnail and CSS class correctly for video path, image path, and empty string.
- Unit: Bundled clip scanner returns correct category → clip mapping from a fixture directory.
- Unit: Gallery tab correctly filters `media_type == "video"` for motion picker and returns all records for character picker.
- Unit: Mode description bar shows correct text and CSS class for each hover target.
- Integration: gallery card "💃 Animate" action switches source to animate and populates character input.
- Integration: gallery card "↗ Motion" action populates motion input without switching source.
- Manual: hover slide-up bar appears/disappears smoothly on video and image cards; does not appear on cards with no `video_path`.
