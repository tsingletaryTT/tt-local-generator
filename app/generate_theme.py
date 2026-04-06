#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
#
# generate_theme.py — Thematic 5-shot prompt generator.
#
# Generates a cohesive set of 5 video prompts sharing a meta-goal (director,
# genre, mood, or product aesthetic).  Each set forms a narrative arc:
#   establish → develop → develop → climax → resolve
#
# Qwen3-0.6B is asked to produce all 5 shots in a single call, which keeps the
# shots coherent and avoids the latency of 5 sequential calls.  The LLM is
# prompted for numbered lines (not JSON) — far more reliably produced by small
# models.  A two-stage parser (JSON probe → line-by-line) covers both paths.
#
# Usage:
#   python3 generate_theme.py
#   python3 generate_theme.py --theme hitchcock
#   python3 generate_theme.py --list-themes
#   python3 generate_theme.py --raw
#   python3 generate_theme.py --no-enhance

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import word_banks as wb

# ── Server config (mirrors generate_prompt.py) ────────────────────────────────

LLM_URL    = "http://127.0.0.1:8001/v1/chat/completions"
LLM_MODEL  = "Qwen/Qwen3-0.6B"
LLM_HEALTH = "http://127.0.0.1:8001/health"

# ── Shot roles ─────────────────────────────────────────────────────────────────

SHOT_ROLES = ["establish", "develop", "develop", "climax", "resolve"]

# Camera pools filtered by narrative intensity — the early shots stay wide and
# grounded; later shots get tighter and more expressive.
_CAMERA_BY_ROLE = {
    "establish": [
        "wide establishing shot", "static wide", "aerial wide",
        "long lens, shallow focus", "slow pull-back",
    ],
    "develop": [
        "medium shot, slow push-in", "over-the-shoulder", "tracking shot",
        "handheld follow", "low angle medium",
    ],
    "climax": [
        "extreme close-up", "tight close-up", "Dutch angle close-up",
        "macro close-up", "low angle upshot",
    ],
    "resolve": [
        "wide pull-back", "slow pull-back to wide", "aerial pull-out",
        "static wide — empty space", "long lens — figure small in frame",
    ],
}

_MOOD_BY_ROLE = {
    "establish": ["calm", "quiet", "still", "grounded", "unhurried"],
    "develop":   ["uneasy", "tense", "watchful", "uncertain", "restless"],
    "develop2":  ["unsettling", "foreboding", "eerie", "charged", "wrong"],
    "climax":    ["stark", "overwhelming", "violent", "ecstatic", "fracturing"],
    "resolve":   ["quiet aftermath", "muted", "exhausted", "distant", "still"],
}

def _role_mood(role: str, shot_index: int) -> str:
    key = "develop2" if role == "develop" and shot_index == 2 else role
    pool = _MOOD_BY_ROLE.get(key, _MOOD_BY_ROLE["develop"])
    return random.choice(pool)

def _role_camera(role: str) -> str:
    return random.choice(_CAMERA_BY_ROLE[role])

# ── Theme library ──────────────────────────────────────────────────────────────

@dataclass
class ThemeSpec:
    label: str               # UI display name
    description: str         # brief used in the LLM user message
    style_anchor: str        # injected into every slug and into the LLM brief
    # style_lock: if set, appended to every slug as the style slot.
    # If None, style_sequence (one entry per shot) is used instead.
    style_lock: "str | None" = None
    style_sequence: "list[str] | None" = None
    subject_register: str = "general"
    setting_register: str = "general"
    climax_modifier: str = "extreme close-up, held breath"
    # Optional overrides for subject / setting per shot index.
    # If None, subject/setting are sampled from the named register for every shot.
    subject_sequence: "list[str] | None" = None
    setting_sequence: "list[str] | None" = None


THEME_LIBRARY: dict[str, ThemeSpec] = {

    # ── Director-anchored ─────────────────────────────────────────────────────

    "hitchcock": ThemeSpec(
        label="Hitchcock: Rear Window",
        description=(
            "A voyeuristic thriller in black and white — "
            "someone is watching, something is wrong, the tension builds shot by shot."
        ),
        style_anchor="black and white, voyeuristic high-angle, chiaroscuro, 1950s suspense",
        style_lock="Hitchcock — voyeuristic high-angle, chiaroscuro, 1950s B&W thriller",
        subject_register="kafka",
        setting_register="suburban_unease",
        climax_modifier="extreme close-up, shaking hands, venetian-blind shadow bars",
    ),

    "tarkovsky": ThemeSpec(
        label="Tarkovsky: The Zone",
        description=(
            "Five slow meditations on landscape and longing — "
            "water, fire, memory, the weight of waiting."
        ),
        style_anchor="long take, transcendent water and fire, Soviet grey-green palette",
        style_lock="Tarkovsky — slow-burn long take, transcendent water and fire",
        subject_register="steinbeck",
        setting_register="impossible",
        climax_modifier="figure submerged in still water, camera stationary, silence",
    ),

    "wong_kar_wai": ThemeSpec(
        label="Wong Kar-wai: Missed Connections",
        description=(
            "Neon longing, slow-motion near-touches, Hong Kong at 2am — "
            "two people who never quite arrive at the same moment."
        ),
        style_anchor="neon overexposure, slow-motion, blur, saturated 1990s Hong Kong",
        style_lock="Wong Kar-wai — neon overexposure, slow-motion, saturated 1990s",
        subject_register="robbins",
        setting_register="music_video",
        climax_modifier="frozen frame, hand almost touching, out-of-focus neon bloom",
    ),

    "kubrick": ThemeSpec(
        label="Kubrick: The Long Corridor",
        description=(
            "Sterile symmetry and quiet menace — a figure moves through "
            "institutional space toward something inevitable."
        ),
        style_anchor="Kubrick — one-point perspective, symmetrical framing, sterile dread",
        style_lock="Kubrick — one-point perspective, symmetrical framing, clinical menace",
        subject_register="pkd",
        setting_register="kafka",
        climax_modifier="perfect symmetrical corridor, tiny figure at vanishing point",
    ),

    "lynch": ThemeSpec(
        label="Lynch: The Diner at 3am",
        description=(
            "American surfaces with wrong interiors — a diner, a hallway, "
            "a woman who knows something she shouldn't."
        ),
        style_anchor="Lynch — deep-focus mundane uncanny, red drapes, backwards-talking",
        style_lock="Lynch — deep-focus mundane uncanny, tungsten warmth, hidden horror",
        subject_register="pkd",
        setting_register="retro_tv",
        climax_modifier="face in extreme close-up, backwards speech implied, red drapes behind",
    ),

    # ── Genre / mood ──────────────────────────────────────────────────────────

    "cosmic_horror": ThemeSpec(
        label="Cosmic Horror: The Geometry Is Wrong",
        description=(
            "Five shots of ordinary spaces slowly revealing something wrong — "
            "the angles don't match, the scale is off, there is no explanation."
        ),
        style_anchor="desaturated, extreme depth-of-field, Lovecraftian dread",
        style_lock=None,
        style_sequence=[
            "35mm grain, realistic",
            "35mm grain, slight colour cast",
            "Haneke — clinical interior, flat affect",
            "deep focus, low angle, something huge in frame",
            "Ansel Adams zone system, monochrome, enormous scale",
        ],
        subject_register="pkd",
        setting_register="dread",
        climax_modifier="non-Euclidean corridor, figure occupies one pixel of frame",
    ),

    "golden_hour_western": ThemeSpec(
        label="Golden Hour Western",
        description=(
            "A lone figure crosses a landscape as the sun dies — "
            "five stations of the classical American myth."
        ),
        style_anchor="1970s Kodachrome, golden-hour backlit silhouette, Leone wide-screen",
        style_lock="1970s Kodachrome, Leone wide-screen",
        subject_register="steinbeck",
        setting_register="american_realism",
        climax_modifier="extreme wide, lone figure, lens flare direct into camera",
    ),

    "vhs_nightmare": ThemeSpec(
        label="VHS Nightmare: 3am Cable",
        description=(
            "Something you half-remember seeing on late-night television when you were nine — "
            "the tracking is off, the colour is wrong, something moves when it shouldn't."
        ),
        style_anchor="vintage VHS texture, scan lines, oversaturated, 1987 practical horror",
        style_lock="vintage VHS texture, scan-line corruption",
        subject_register="king",
        setting_register="retro_tv",
        climax_modifier="tracking glitch freeze, face half-visible in static, single frame",
    ),

    "liminal": ThemeSpec(
        label="Liminal Spaces: The Between Hours",
        description=(
            "Empty transit spaces at 4am — airports, parking structures, hotel corridors — "
            "the world between destinations, a figure who belongs nowhere."
        ),
        style_anchor="fluorescent overexposure, institutional carpet, wrong-hour emptiness",
        style_lock="Fincher — dark precision, obsessive negative-fill lighting",
        subject_register="kafka",
        setting_register="suburban_unease",
        climax_modifier="figure at end of infinite corridor, single lit door at vanishing point",
    ),

    "nature_doc": ThemeSpec(
        label="Attenborough: The Quiet World",
        description=(
            "Five macro and wide shots forming a single ecosystem story — "
            "no humans, only scale and patience."
        ),
        style_anchor="BBC natural history, macro lens, shallow depth, Attenborough pacing",
        style_lock="photorealistic, BBC natural history, macro",
        subject_register="brautigan",
        setting_register="gentle_elsewhere",
        climax_modifier="extreme macro, single organism fills frame, held four seconds",
    ),

    # ── Product / commercial ──────────────────────────────────────────────────

    "product_luxury": ThemeSpec(
        label="Luxury Product: The Object Desires",
        description=(
            "Five product shots that make an ordinary object feel mythological — "
            "the product is the protagonist, light is the drama."
        ),
        style_anchor="one-light warehouse photography, negative fill, velvet surface, macro",
        style_lock="one-light warehouse photography, hero product shot",
        subject_register="commercial",
        setting_register="retro_objects",
        climax_modifier="extreme macro on material texture, single catch-light, held still",
    ),

    "product_nostalgia": ThemeSpec(
        label="Mail-Order Catalog: 1978",
        description=(
            "Five warm product spots in the style of a 1978 Sears catalog shoot — "
            "the product is wonderful, the background is avocado green."
        ),
        style_anchor="Topps card photography 1978, warm tungsten, avocado-green background",
        style_lock="Topps card photography 1978, warm tungsten",
        subject_register="commercial",
        setting_register="nostalgia",
        climax_modifier="hero shot center-frame, starburst graphic implied, product perfect",
    ),

    # ── Animation / stylized ─────────────────────────────────────────────────

    "ghibli": ThemeSpec(
        label="Ghibli: The Long Walk Home",
        description=(
            "A small character travels through an oversized world — "
            "five stations of wonder and quiet enormity."
        ),
        style_anchor="Studio Ghibli, soft watercolor, natural light, hand-drawn detail",
        style_lock="Studio Ghibli-inspired, watercolor, natural golden light",
        subject_register="brautigan",
        setting_register="gentle_elsewhere",
        climax_modifier="vast wide vista, tiny figure in foreground, clouds racing",
    ),

    "psychedelia": ThemeSpec(
        label="1968 Psychedelia: The Expanding Mind",
        description=(
            "Five shots of a consciousness dissolving into colour — "
            "Peter Max meets 2001, Yellow Submarine meets Fantasia."
        ),
        style_anchor="Peter Max psychedelia, Yellow Submarine flat colour, kaleidoscope",
        style_lock=None,
        style_sequence=[
            "Peter Max psychedelia, flat graphic colour",
            "Yellow Submarine animation style",
            "MTV 1984 video aesthetic, saturated",
            "EC Comics horror illustration, vivid",
            "Peter Max psychedelia, figure dissolves into pure colour",
        ],
        subject_register="robbins",
        setting_register="psychedelia",
        climax_modifier="mandala implosion, full-frame colour field, figure dissolves",
    ),

    # ── Decade hop (intentionally varying style) ──────────────────────────────

    "decade_hop": ThemeSpec(
        label="A Century of Cinema: 1920–2020",
        description=(
            "The same street corner across a hundred years of cinema — "
            "silent film through digital, one location five eras."
        ),
        style_anchor="evolving cinematic style — one era per shot",
        style_lock=None,
        style_sequence=[
            "1920s German Expressionism — high contrast, painted shadows",
            "Douglas Sirk — Technicolor melodrama, 1955",
            "Cinema verité 16mm, handheld, France 1965",
            "1970s Kodachrome, New Hollywood grain",
            "Nolan — IMAX grain, fractured geometry, present day",
        ],
        subject_register="general",
        setting_register="american_realism",
        climax_modifier="New Hollywood 70s grain, raw confrontation, handheld",
    ),
}

# ── Algorithmic slug builder ───────────────────────────────────────────────────

def _subject_for_spec(spec: ThemeSpec, i: int) -> str:
    """Pick a subject from the spec's register."""
    if spec.subject_sequence and i < len(spec.subject_sequence):
        return spec.subject_sequence[i]
    reg = getattr(wb, f"SUBJECTS_{spec.subject_register.upper()}", None)
    if reg:
        return random.choice(reg)
    return wb.subject()


def _setting_for_spec(spec: ThemeSpec, i: int) -> str:
    """Pick a setting from the spec's register."""
    if spec.setting_sequence and i < len(spec.setting_sequence):
        return spec.setting_sequence[i]
    reg = getattr(wb, f"SETTINGS_{spec.setting_register.upper()}", None)
    if reg:
        return random.choice(reg)
    return wb.setting()


def _style_for_spec(spec: ThemeSpec, i: int) -> str:
    """Return the style string for shot i."""
    if spec.style_lock:
        return spec.style_lock
    if spec.style_sequence and i < len(spec.style_sequence):
        return spec.style_sequence[i]
    return spec.style_anchor


def _build_slugs(spec: ThemeSpec) -> list[str]:
    """
    Build 5 algorithmic slugs, one per shot role.

    Each slug encodes the appropriate camera move, subject, setting, style,
    and intensity marker for its position in the narrative arc.
    """
    slugs = []
    for i, role in enumerate(SHOT_ROLES):
        subj  = _subject_for_spec(spec, i)
        act   = wb.action()
        cam   = _role_camera(role)
        mood  = _role_mood(role, i)
        style = _style_for_spec(spec, i)

        if role == "climax":
            # Climax slug uses the spec's climax_modifier instead of generic mood.
            slug = f"{subj} {act}, {cam}, {spec.climax_modifier}, {style}"
        else:
            slug = f"{subj} {act}, {cam}, {mood}, {style}"

        slugs.append(slug)
    return slugs

# ── LLM health check ──────────────────────────────────────────────────────────

def _llm_available() -> bool:
    try:
        with urllib.request.urlopen(LLM_HEALTH, timeout=3) as r:
            data = json.loads(r.read())
        return data.get("model_ready", False)
    except Exception:
        return False

# ── LLM call: single request for all 5 shots ─────────────────────────────────

_THEME_SYSTEM = (
    "You are a cinematic prompt writer for AI video generation. "
    "Your output must be exactly 5 numbered lines, one prompt per line. "
    "Format: '1. [prompt]', '2. [prompt]', etc. "
    "Each prompt: one subject, one action, one location. Hard limit: 22 words each. "
    "No preamble. No JSON. No quotes around lines. No extra text."
)

_SHOT_ROLE_HINTS = [
    "Shot 1 [establish] — wide, grounded, literal. Introduce the world.",
    "Shot 2 [develop]   — medium, slight unease. Something shifts.",
    "Shot 3 [develop]   — tighter, mood intensifies. Something is wrong.",
    "Shot 4 [climax]    — close-up, peak atmosphere. The decisive moment.",
    "Shot 5 [resolve]   — pull back, quiet aftermath. The world after.",
]


def _llm_theme_shots(
    slugs: list[str],
    spec: ThemeSpec,
    timeout: int = 90,
) -> "list[str] | None":
    """
    Send all 5 slugs to Qwen in one call.  Returns list of 5 prompt strings,
    or None if the call fails or produces unusable output.
    """
    shot_lines = "\n".join(
        f"{hint}\nSeed: {slug}"
        for hint, slug in zip(_SHOT_ROLE_HINTS, slugs)
    )
    user_msg = (
        f"Theme: {spec.description}\n"
        f"Style anchor (apply to all shots): {spec.style_anchor}\n\n"
        f"Rewrite each seed as a vivid prompt, keeping all named elements. "
        f"Maintain the style anchor throughout. Build intensity shot by shot.\n\n"
        f"{shot_lines}"
    )

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": _THEME_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": 220,   # ~44 tokens × 5 shots with headroom
        "temperature": 0.75,
        "top_p": 0.92,
    }).encode()

    req = urllib.request.Request(
        LLM_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read())
        raw = resp["choices"][0]["message"]["content"].strip()
        return _parse_llm_response(raw, slugs)
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError,
            OSError):
        return None

# ── Response parser ───────────────────────────────────────────────────────────

def _parse_llm_response(raw: str, fallback_slugs: list[str]) -> "list[str] | None":
    """
    Two-stage parser for Qwen's themed output.

    Stage 1 — JSON probe: if the model decided to return JSON anyway, handle it.
    Stage 2 — Line parser (primary path): strip numbering, collect 5 lines.

    Any missing shots are padded with the corresponding algorithmic slug so that
    a partial response (e.g. 3 of 5 lines before timeout) still yields a full set.
    Returns None only if the response is completely empty.
    """
    if not raw:
        return None

    # Stage 1: JSON probe
    try:
        obj = json.loads(raw)
        if isinstance(obj, list):
            prompts = [str(x) for x in obj if x]
            if len(prompts) >= 1:
                # Pad to 5 with slugs
                while len(prompts) < 5:
                    prompts.append(fallback_slugs[len(prompts)])
                return prompts[:5]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting JSON array from within a larger response
    import re
    m = re.search(r'\[.*?\]', raw, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, list):
                prompts = [str(x) for x in obj if x]
                if len(prompts) >= 1:
                    while len(prompts) < 5:
                        prompts.append(fallback_slugs[len(prompts)])
                    return prompts[:5]
        except (json.JSONDecodeError, TypeError):
            pass

    # Stage 2: numbered-line parser
    prompts: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading: "1.", "1)", "(1)", "- ", "• ", etc.
        cleaned = re.sub(r'^[\d]+[.)]\s*|^[-•]\s*|\([0-9]+\)\s*', '', line).strip()
        if len(cleaned) < 8:
            continue
        prompts.append(cleaned)
        if len(prompts) == 5:
            break

    if not prompts:
        return None

    # Pad any missing shots with their algorithmic slugs
    while len(prompts) < 5:
        prompts.append(fallback_slugs[len(prompts)])

    return prompts[:5]

# ── Top-level generator ───────────────────────────────────────────────────────

def generate_theme(
    theme_key: str = "",
    enhance: bool = True,
) -> dict:
    """
    Generate a thematic set of 5 video prompts.

    Args:
        theme_key: key from THEME_LIBRARY, or "" to pick randomly.
        enhance:   if True and LLM is available, use Qwen to polish the slugs.

    Returns:
        {
            "theme":     str,           # display label
            "theme_key": str,           # THEME_LIBRARY key
            "source":    "llm"|"algo",  # whether LLM was used
            "shots": [
                {
                    "shot":   int,      # 1-based
                    "role":   str,      # establish/develop/climax/resolve
                    "prompt": str,      # final prompt
                    "slug":   str,      # pre-polish algorithmic slug
                },
                ...  # exactly 5 items
            ]
        }
    """
    if not theme_key or theme_key not in THEME_LIBRARY:
        theme_key = random.choice(list(THEME_LIBRARY.keys()))
    spec = THEME_LIBRARY[theme_key]

    slugs = _build_slugs(spec)
    source = "algo"
    prompts = slugs[:]

    if enhance and _llm_available():
        llm_result = _llm_theme_shots(slugs, spec)
        if llm_result:
            prompts = llm_result
            source = "llm"

    shots = [
        {
            "shot":   i + 1,
            "role":   SHOT_ROLES[i],
            "prompt": prompts[i],
            "slug":   slugs[i],
        }
        for i in range(5)
    ]

    return {
        "theme":     spec.label,
        "theme_key": theme_key,
        "source":    source,
        "shots":     shots,
    }

# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a 5-shot thematic prompt set (algo → LLM).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 generate_theme.py
  python3 generate_theme.py --theme hitchcock
  python3 generate_theme.py --theme vhs_nightmare --no-enhance
  python3 generate_theme.py --list-themes
  python3 generate_theme.py --raw
        """,
    )
    parser.add_argument(
        "--theme", default="",
        help="Theme key (default: random). Use --list-themes to see options.",
    )
    parser.add_argument(
        "--list-themes", action="store_true",
        help="Print available theme keys and exit.",
    )
    parser.add_argument(
        "--enhance", action=argparse.BooleanOptionalAction, default=True,
        help="Polish slugs with the LLM (default: on).",
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Print prompts only (one per line), no JSON wrapper.",
    )
    args = parser.parse_args()

    if args.list_themes:
        for key, spec in THEME_LIBRARY.items():
            print(f"  {key:<22}  {spec.label}")
        return

    result = generate_theme(theme_key=args.theme, enhance=args.enhance)

    if args.raw:
        for shot in result["shots"]:
            print(shot["prompt"])
        return

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
