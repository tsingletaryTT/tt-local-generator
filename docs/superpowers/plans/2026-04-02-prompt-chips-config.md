# Prompt Chips YAML Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move hardcoded prompt chip lists out of `main_window.py` into `config/prompt_chips.yaml`, add a `chip_config.py` loader module, and update the UI to render chips in named category groups with vertical wrapping layout.

**Architecture:** New `chip_config.py` module loads and filters chips at startup; `main_window.py` calls it once and stores the result; the existing `_make_chips_box()` is rewritten to produce a vertical `Gtk.FlowBox`-per-category layout. Zero GTK dependencies outside `main_window.py`.

**Tech Stack:** Python 3 dataclasses, PyYAML, GTK4 `Gtk.FlowBox`, pytest.

---

## File Map

| File | Action |
|------|--------|
| `chip_config.py` | Create — `ChipEntry`, `ChipCategory` dataclasses + `load_chips()` |
| `config/prompt_chips.yaml` | Create — all chip definitions migrated from Python lists |
| `tests/test_chip_config.py` | Create — pytest unit tests for `chip_config.py` (no GTK) |
| `main_window.py` | Remove `_PROMPT_CHIPS`/`_IMAGE_PROMPT_CHIPS`; add `_load_chips_safe()`; rewrite `_make_chips_box()`; update scroll policy; add CSS |

---

## Task 1: `chip_config.py` — loader module with TDD

**Files:**
- Create: `chip_config.py`
- Create: `tests/test_chip_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chip_config.py`:

```python
"""Tests for chip_config.py — zero GTK dependencies."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path
from chip_config import load_chips, ChipEntry, ChipCategory

FIXTURES = Path(__file__).parent / "fixtures"

def _yaml(content: str, tmp_path: Path) -> Path:
    p = tmp_path / "chips.yaml"
    p.write_text(content)
    return p


# ── load_chips() basic filtering ─────────────────────────────────────────────

def test_load_chips_returns_categories_for_tab(tmp_path):
    p = _yaml("""
- name: Camera
  for: [video, animate]
  chips:
    - label: "🎥 cinematic"
      text: "cinematic shot"
      tip: "Wide-format filmic look"
""", tmp_path)
    cats = load_chips("video", p)
    assert len(cats) == 1
    assert cats[0].name == "Camera"
    assert cats[0].chips[0].label == "🎥 cinematic"
    assert cats[0].chips[0].text == "cinematic shot"
    assert cats[0].chips[0].tip == "Wide-format filmic look"


def test_category_excluded_when_tab_not_in_for(tmp_path):
    p = _yaml("""
- name: Camera
  for: [video]
  chips:
    - label: "🎥 cinematic"
      text: "cinematic shot"
""", tmp_path)
    cats = load_chips("image", p)
    assert cats == []


def test_category_for_defaults_to_all_tabs(tmp_path):
    p = _yaml("""
- name: Quality
  chips:
    - label: "✨ 4K"
      text: "4K, ultra-detailed"
""", tmp_path)
    for tab in ("video", "image", "animate"):
        cats = load_chips(tab, p)
        assert len(cats) == 1, f"Expected category for tab={tab}"


# ── chip-level for: override ──────────────────────────────────────────────────

def test_chip_level_for_overrides_category_for(tmp_path):
    p = _yaml("""
- name: Lighting
  for: [video, animate]
  chips:
    - label: "💡 studio"
      text: "studio lighting"
      for: [image]
""", tmp_path)
    # Category says video+animate, chip says image — chip wins
    image_cats = load_chips("image", p)
    assert len(image_cats) == 1
    assert image_cats[0].chips[0].label == "💡 studio"

    video_cats = load_chips("video", p)
    assert video_cats == []   # chip-level for=[image] excludes video


def test_chip_level_for_does_not_merge_with_category(tmp_path):
    """chip-level for: replaces (not merges with) category for:."""
    p = _yaml("""
- name: Style
  for: [video]
  chips:
    - label: "🌈 vibrant"
      text: "vibrant colors"
      for: [image]
    - label: "🎞 film grain"
      text: "35mm film grain"
""", tmp_path)
    video_cats = load_chips("video", p)
    # Only the chip without an override should appear
    assert len(video_cats) == 1
    assert len(video_cats[0].chips) == 1
    assert video_cats[0].chips[0].label == "🎞 film grain"


def test_categories_with_no_matching_chips_excluded(tmp_path):
    p = _yaml("""
- name: VideoOnly
  for: [video]
  chips:
    - label: "🚁 aerial"
      text: "aerial drone shot"
- name: ImageOnly
  for: [image]
  chips:
    - label: "💡 studio"
      text: "studio lighting"
""", tmp_path)
    cats = load_chips("animate", p)
    assert cats == []


# ── tip default ───────────────────────────────────────────────────────────────

def test_tip_defaults_to_empty_string(tmp_path):
    p = _yaml("""
- name: Style
  chips:
    - label: "🎞 grain"
      text: "film grain"
""", tmp_path)
    cats = load_chips("video", p)
    assert cats[0].chips[0].tip == ""


# ── error cases ───────────────────────────────────────────────────────────────

def test_missing_yaml_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_chips("video", tmp_path / "nonexistent.yaml")


def test_malformed_yaml_missing_label_raises_value_error(tmp_path):
    p = _yaml("""
- name: Style
  chips:
    - text: "film grain"
""", tmp_path)
    with pytest.raises(ValueError, match="label"):
        load_chips("video", p)


def test_malformed_yaml_missing_text_raises_value_error(tmp_path):
    p = _yaml("""
- name: Style
  chips:
    - label: "🎞 grain"
""", tmp_path)
    with pytest.raises(ValueError, match="text"):
        load_chips("video", p)


def test_empty_yaml_returns_empty_list(tmp_path):
    p = _yaml("", tmp_path)
    assert load_chips("video", p) == []
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd ~/code/tt-local-generator
python3 -m pytest tests/test_chip_config.py -v 2>&1 | head -40
```

Expected: All 11 tests fail with `ModuleNotFoundError: No module named 'chip_config'`.

- [ ] **Step 3: Create `chip_config.py`**

Create `chip_config.py` at the repo root:

```python
"""chip_config.py — Load prompt chip definitions from config/prompt_chips.yaml.

Public API:
    ChipEntry     — dataclass: label, text, tip
    ChipCategory  — dataclass: name, chips
    load_chips(tab, config_path=None) -> list[ChipCategory]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).parent
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "prompt_chips.yaml"
_ALL_TABS = frozenset({"video", "image", "animate"})


@dataclass
class ChipEntry:
    label: str          # button label (may include emoji)
    text: str           # text appended to prompt on click
    tip: str = ""       # tooltip (empty string if omitted)


@dataclass
class ChipCategory:
    name: str                    # display name shown as group header
    chips: list[ChipEntry] = field(default_factory=list)


def load_chips(tab: str, config_path: Path | None = None) -> list[ChipCategory]:
    """Load chip categories for *tab* ('video', 'image', or 'animate').

    config_path defaults to <repo_root>/config/prompt_chips.yaml.
    Categories with no chips matching *tab* after filtering are omitted.

    Raises:
        FileNotFoundError: config file does not exist
        ValueError: schema error (missing required field)
    """
    path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Chip config not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return []

    result: list[ChipCategory] = []
    for cat_idx, cat_raw in enumerate(data):
        cat_name = cat_raw.get("name")
        if not cat_name:
            raise ValueError(f"Category at index {cat_idx} is missing required field 'name'")

        # Category-level for: defaults to all tabs
        cat_for = set(cat_raw.get("for", list(_ALL_TABS)))

        chips_raw = cat_raw.get("chips", [])
        matched: list[ChipEntry] = []
        for chip_idx, chip_raw in enumerate(chips_raw):
            label = chip_raw.get("label")
            if not label:
                raise ValueError(
                    f"Chip at category '{cat_name}' index {chip_idx} is missing required field 'label'"
                )
            text = chip_raw.get("text")
            if text is None:
                raise ValueError(
                    f"Chip at category '{cat_name}' index {chip_idx} is missing required field 'text'"
                )

            # Chip-level for: replaces (does not merge with) category for:
            if "for" in chip_raw:
                effective_for = set(chip_raw["for"])
            else:
                effective_for = cat_for

            if tab in effective_for:
                matched.append(ChipEntry(
                    label=label,
                    text=text,
                    tip=chip_raw.get("tip", ""),
                ))

        if matched:
            result.append(ChipCategory(name=cat_name, chips=matched))

    return result
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd ~/code/tt-local-generator
python3 -m pytest tests/test_chip_config.py -v
```

Expected: All 11 tests pass.

- [ ] **Step 5: Commit**

```bash
cd ~/code/tt-local-generator
git add chip_config.py tests/test_chip_config.py
git commit -m "feat: add chip_config.py loader and pytest unit tests"
```

---

## Task 2: Create `config/prompt_chips.yaml`

**Files:**
- Create: `config/prompt_chips.yaml`

Migrate every chip from `_PROMPT_CHIPS` (line 346) and `_IMAGE_PROMPT_CHIPS` (line 382) in `main_window.py` into YAML. Assign `for:` to categories:
- Camera, Lighting (shared names), Motion/Mood, and the video-only quality chips → `for: [video, animate]`
- Video-only Quality chips → `for: [video, animate]`
- Animate tab gets the same chips as video (motion vocabulary is relevant)
- Image-only Artistic Style and Image Composition/Quality → `for: [image]`
- Chips that appear in **both** lists with identical label/text (golden hour, dramatic, moonlit, candlelit, neon, film grain, noir, vibrant, cold tones, rule of thirds, depth of field, close-up, wide shot, cinematic/photorealistic) → single entry `for: [video, image, animate]` or `for: [video, image]` as appropriate, deduplicating

- [ ] **Step 1: Create `config/` directory and `prompt_chips.yaml`**

```bash
mkdir -p ~/code/tt-local-generator/config
```

Create `config/prompt_chips.yaml`:

```yaml
# Prompt style chips for tt-local-generator
# Each category has an optional `for:` list of tab keys: video, image, animate.
# Default (no `for:`) = shown on all tabs.
# Each chip can also have `for:` which overrides its category's `for:`.

# ── Camera / Shot ─────────────────────────────────────────────────────────────
# Video + animate share motion/camera vocabulary; image has a few camera chips too.

- name: Camera / Shot
  for: [video, animate]
  chips:
    - label: "🎥 cinematic"
      text: "cinematic shot"
      tip: "Wide-format filmic look"

    - label: "🚁 aerial"
      text: "aerial drone shot"
      tip: "Top-down or bird's-eye view"

    - label: "🔭 dolly in"
      text: "slow dolly in"
      tip: "Camera glides forward"

    - label: "↩ pan left"
      text: "slow pan left"
      tip: "Camera sweeps left"

    - label: "🔄 orbit"
      text: "orbiting camera"
      tip: "Camera circles the subject"

    - label: "📷 close-up"
      text: "extreme close-up"
      tip: "Tight shot on subject"
      for: [video, animate, image]

    - label: "🏔 wide shot"
      text: "wide establishing shot"
      tip: "Full scene context"
      for: [video, animate, image]

    - label: "👁 POV"
      text: "point of view shot"
      tip: "First-person perspective"

# ── Lighting ──────────────────────────────────────────────────────────────────
# Shared across all tabs.

- name: Lighting
  chips:
    - label: "🌅 golden hour"
      text: "golden hour lighting"
      tip: "Warm sunrise/sunset glow"

    - label: "🌙 moonlit"
      text: "moonlight, night scene"
      tip: "Cool blue-silver night light"

    - label: "💡 neon"
      text: "neon-lit, cyberpunk lighting"
      tip: "Vivid colored neon signs"

    - label: "⚡ dramatic"
      text: "dramatic chiaroscuro lighting"
      tip: "High contrast light and shadow"

    - label: "☀ harsh noon"
      text: "harsh noon sunlight, overexposed"
      tip: "Bright midday bleaching"
      for: [video, animate]

    - label: "🕯 candlelit"
      text: "warm candlelight, flickering"
      tip: "Intimate low orange light"

    - label: "💡 studio"
      text: "studio lighting, soft box"
      tip: "Clean professional lighting"
      for: [image]

# ── Motion / Mood ─────────────────────────────────────────────────────────────
# Video and animate only — these describe temporal dynamics irrelevant to images.

- name: Motion / Mood
  for: [video, animate]
  chips:
    - label: "🌊 slow motion"
      text: "slow motion, 240fps look"
      tip: "Stretched, fluid movement"

    - label: "⏩ time-lapse"
      text: "time-lapse, sped-up motion"
      tip: "Fast-forwarded world"

    - label: "🌬 windy"
      text: "strong wind, hair and leaves moving"
      tip: "Environmental motion cues"

    - label: "🔥 intense"
      text: "intense, high energy, dynamic"
      tip: "Kinetic, fast-paced feel"

    - label: "😌 calm"
      text: "calm, serene, peaceful atmosphere"
      tip: "Tranquil, slow-moving"

# ── Artistic Style ────────────────────────────────────────────────────────────
# Shared — style descriptors work for both images and video.

- name: Artistic Style
  chips:
    - label: "🎞 film grain"
      text: "35mm film grain, analog"
      tip: "Vintage celluloid texture"

    - label: "🖤 noir"
      text: "black and white, film noir"
      tip: "High-contrast monochrome"

    - label: "🎨 painterly"
      text: "painterly, impressionist style"
      tip: "Brushstroke, artistic look"
      for: [video, animate]

    - label: "🌈 vibrant"
      text: "vibrant colors, oversaturated"
      tip: "Bold, punchy color grading"

    - label: "🧊 cold tones"
      text: "cold color grading, blue tones"
      tip: "Icy, desaturated blues"

    - label: "🎨 oil painting"
      text: "oil painting, thick brushstrokes"
      tip: "Classic oil painting style"
      for: [image]

    - label: "🖋 line art"
      text: "detailed line art"
      tip: "Clean ink illustration"
      for: [image]

    - label: "🔮 fantasy"
      text: "fantasy art, magical atmosphere"
      tip: "Otherworldly, mystical look"
      for: [image]

    - label: "🎭 concept art"
      text: "concept art, digital painting"
      tip: "Professional concept illustration"
      for: [image]

# ── Quality / Composition ─────────────────────────────────────────────────────
# Shared across all tabs.

- name: Quality / Composition
  chips:
    - label: "✨ 4K"
      text: "4K, ultra-detailed, sharp"
      tip: "High resolution detail"
      for: [video, animate]

    - label: "✨ ultra detail"
      text: "ultra-detailed, 8K, sharp"
      tip: "Maximum detail and resolution"
      for: [image]

    - label: "📐 rule of thirds"
      text: "rule of thirds composition"
      tip: "Classic photographic framing"

    - label: "🌁 depth of field"
      text: "shallow depth of field, bokeh"
      tip: "Blurred background, sharp subject"

    - label: "🎭 photorealistic"
      text: "photorealistic, hyperrealistic"
      tip: "Looks like real footage"

    - label: "🔲 symmetrical"
      text: "perfectly symmetrical composition"
      tip: "Mirror-perfect balance"
      for: [image]
```

- [ ] **Step 2: Smoke-test the YAML with `chip_config.py`**

```bash
cd ~/code/tt-local-generator
python3 -c "
from chip_config import load_chips
for tab in ('video', 'image', 'animate'):
    cats = load_chips(tab)
    total = sum(len(c.chips) for c in cats)
    print(f'{tab}: {len(cats)} categories, {total} chips')
    for c in cats:
        print(f'  {c.name}: {[ch.label for ch in c.chips]}')
"
```

Expected (approximate — check counts make sense, no errors):
```
video: 4 categories, ~27 chips
image: 4 categories, ~20 chips
animate: 4 categories, ~27 chips
```

No exceptions. Each chip in each tab should have appropriate labels.

- [ ] **Step 3: Commit**

```bash
cd ~/code/tt-local-generator
git add config/prompt_chips.yaml
git commit -m "feat: add config/prompt_chips.yaml with migrated chip definitions"
```

---

## Task 3: Update `main_window.py`

**Files:**
- Modify: `main_window.py`

Remove the two Python list constants, add safe loader at module level, rewrite `_make_chips_box()` with category groups and `Gtk.FlowBox`, update scroll policy, add CSS class.

- [ ] **Step 1: Add import and `_load_chips_safe()` at module level; remove old constants**

In `main_window.py`, find the import block near the top (before `_PROMPT_CHIPS` at line 346). Add after existing imports:

```python
import sys
from chip_config import load_chips as _load_chips
```

(Note: `sys` may already be imported — check first and only add if absent.)

Then find and remove the block from line 342 to 408 (the `_PROMPT_CHIPS` and `_IMAGE_PROMPT_CHIPS` lists plus their header comment). Replace that entire block with:

```python
# ── Prompt component chips ────────────────────────────────────────────────────
# Loaded once at startup from config/prompt_chips.yaml via chip_config.py.
# Falls back to empty list if the file is missing or malformed.

def _load_chips_safe(tab: str) -> list:
    try:
        return _load_chips(tab)
    except Exception as e:
        print(f"Warning: could not load chips for '{tab}': {e}", file=sys.stderr)
        return []

_VIDEO_CHIPS   = _load_chips_safe("video")
_IMAGE_CHIPS   = _load_chips_safe("image")
_ANIMATE_CHIPS = _load_chips_safe("animate")
```

- [ ] **Step 2: Add `.chips-category-lbl` CSS class to `_CSS`**

In `main_window.py`, find the `_CSS` bytes literal. Near the end of the chips-related CSS (look for `.chip-btn`), add:

```css
.chips-category-lbl {
    color: @tt_text_muted;
    font-size: 10px;
    margin-top: 4px;
}
```

- [ ] **Step 3: Rewrite `_make_chips_box()` at line 2365**

Replace the existing method body (lines 2365–2379) with:

```python
    def _make_chips_box(self, source: str) -> Gtk.Box:
        """Build a vertically grouped chip box for *source* ('video'/'image'/'animate')."""
        categories = {
            "video":   _VIDEO_CHIPS,
            "image":   _IMAGE_CHIPS,
            "animate": _ANIMATE_CHIPS,
        }.get(source, [])

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_margin_start(2)
        outer.set_margin_end(2)
        outer.set_margin_top(2)
        outer.set_margin_bottom(2)

        for cat in categories:
            lbl = Gtk.Label(label=cat.name)
            lbl.set_xalign(0)
            lbl.add_css_class("chips-category-lbl")
            outer.append(lbl)

            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_row_spacing(3)
            flow.set_column_spacing(4)
            for chip in cat.chips:
                btn = Gtk.Button(label=chip.label)
                btn.set_tooltip_text(chip.tip)
                btn.add_css_class("chip-btn")
                btn.connect("clicked", lambda _b, t=chip.text: self._append_to_prompt(t))
                flow.append(btn)
            outer.append(flow)

        return outer
```

- [ ] **Step 4: Update scroll policy in `_build()` at line 1787**

Find:

```python
        self._chips_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
```

Replace with:

```python
        self._chips_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
```

- [ ] **Step 5: Update `_set_source()` to pass `"animate"` for animate tab**

Find line 2119 in `_set_source()`:

```python
        chip_source = "image" if is_image else "video"
        self._chips_scroll.set_child(self._make_chips_box(chip_source))
```

Replace with:

```python
        if is_image:
            chip_source = "image"
        elif is_animate:
            chip_source = "animate"
        else:
            chip_source = "video"
        self._chips_scroll.set_child(self._make_chips_box(chip_source))
```

- [ ] **Step 6: Smoke-test the updated app**

```bash
cd ~/code/tt-local-generator
/usr/bin/python3 main.py &
sleep 3
```

Verify:
1. App opens without traceback or `Warning:` lines on stderr
2. Video tab chips panel shows category headers ("Camera / Shot", "Lighting", etc.) in muted small text
3. Chips wrap into multiple rows (vertical scroll, not horizontal)
4. Clicking a chip appends its text to the prompt
5. Switch to Image tab → different category set appears (no Motion/Mood, has Artistic Style image chips)
6. Switch to Animate tab → same chip set as Video tab appears

```bash
kill %1
```

- [ ] **Step 7: Commit**

```bash
cd ~/code/tt-local-generator
git add main_window.py
git commit -m "refactor: load prompt chips from YAML with category group UI"
```

---

## Verification (end-to-end)

```bash
cd ~/code/tt-local-generator
python3 -m pytest tests/ -v
/usr/bin/python3 main.py
```

Checklist:
- [ ] All tests in `tests/test_chip_config.py` pass (11 tests)
- [ ] All tests in `tests/test_model_attribution.py` pass (10 tests)
- [ ] App opens without warnings or tracebacks
- [ ] Video tab: 4 category sections, chips wrap vertically
- [ ] Image tab: different categories; no Motion/Mood section; image-specific style chips present
- [ ] Animate tab: same as Video tab (shares motion vocabulary)
- [ ] `_PROMPT_CHIPS` and `_IMAGE_PROMPT_CHIPS` no longer exist in `main_window.py`
- [ ] `config/prompt_chips.yaml` is the single source of truth for all chip definitions
