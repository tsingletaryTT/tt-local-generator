# Headless Queue + Prompt-Generation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `tt-ctl queue run` (drain and execute the persistent queue) and `tt-ctl generate [GUIDE]` (generate N prompts then run them) so the full video-generation pipeline works without the GUI; completed records appear in the GUI on next open with no extra steps.

**Architecture:** Two new functions in `tt-ctl` (`cmd_queue_run`, `cmd_generate`) plus a new `guided_generate()` function in `app/generate_prompt.py`. Workers already write to `history.json` in the format the GUI reads, so no GUI changes are needed. `cmd_generate` calls `cmd_queue_run` directly after staging prompts.

**Tech Stack:** Python 3 stdlib only — `threading`, `urllib.request`, `argparse`. Existing workers (`GenerationWorker`, `ImageGenerationWorker`, `AnimateGenerationWorker`), `HistoryStore`, and `APIClient` are reused unchanged.

**Spec:** `docs/superpowers/specs/2026-04-13-headless-queue-pipeline-design.md`

---

## File Map

| File | Change | What it gains |
|---|---|---|
| `app/generate_prompt.py` | Modify (add only) | `_llm_guided()`, `guided_generate()` |
| `tt-ctl` | Modify | `_make_worker_for_item()`, `cmd_queue_run()`, `cmd_generate()`, parser wiring, import additions |
| `tests/test_generate_prompt_guided.py` | Create | Tests for `_llm_guided` and `guided_generate` |
| `tests/test_queue_run.py` | Create | Tests for `cmd_queue_run` (consume, skip, fail, Ctrl+C) |
| `tests/test_generate_cmd.py` | Create | Tests for `cmd_generate` (queue-only, auto-run, seed increment) |

---

## Task 1: `guided_generate()` in `generate_prompt.py`

**Files:**
- Modify: `app/generate_prompt.py` (append after `_llm_polish`)
- Create: `tests/test_generate_prompt_guided.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generate_prompt_guided.py`:

```python
"""Tests for guided_generate() and _llm_guided() in generate_prompt.py."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import generate_prompt as gp


def _fake_urlopen(text: str):
    """Return a context-manager mock that yields a response with the given text."""
    body = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── _llm_guided ──────────────────────────────────────────────────────────────

def test_llm_guided_sends_guide_in_user_message():
    """_llm_guided posts the guide in the user message to the LLM."""
    mock_resp = _fake_urlopen("A golden volcano erupts at dusk, lava rivers glowing")
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = gp._llm_guided("erupting volcano at night", "video")
    assert result == "A golden volcano erupts at dusk, lava rivers glowing"
    call_args = mock_open.call_args
    req = call_args[0][0]
    payload = json.loads(req.data)
    user_msg = payload["messages"][1]["content"]
    assert "erupting volcano at night" in user_msg


def test_llm_guided_uses_type_hint():
    """_llm_guided includes the type-specific hint from _TYPE_HINT in the user message."""
    mock_resp = _fake_urlopen("Bioluminescent jellyfish drift through coral")
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        gp._llm_guided("underwater scene", "skyreels")
    req = mock_open.call_args[0][0]
    payload = json.loads(req.data)
    user_msg = payload["messages"][1]["content"]
    # _TYPE_HINT["skyreels"] mentions cinematic
    assert "cinematic" in user_msg.lower() or "skyreels" in user_msg.lower() or "clip" in user_msg.lower()


def test_llm_guided_returns_none_on_network_error():
    """_llm_guided returns None when the LLM server is unreachable."""
    import urllib.error
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        result = gp._llm_guided("golden cliffs", "video")
    assert result is None


def test_llm_guided_returns_none_on_bad_json():
    """_llm_guided returns None when the response is not valid JSON."""
    resp = MagicMock()
    resp.read.return_value = b"not json {"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        result = gp._llm_guided("golden cliffs", "video")
    assert result is None


# ── guided_generate ──────────────────────────────────────────────────────────

def test_guided_generate_llm_up_returns_llm_result():
    """When Qwen is available, guided_generate returns the LLM-generated prompt."""
    polished = "Lava rivers carve a neon path down obsidian cliffs at midnight"
    with patch.object(gp, "_llm_available", return_value=True), \
         patch.object(gp, "_llm_guided", return_value=polished) as mock_guided:
        result = gp.guided_generate("erupting volcano", "video")
    assert result["prompt"] == polished
    assert result["source"] == "llm"
    assert result["slug"] == "erupting volcano"
    assert result["type"] == "video"
    mock_guided.assert_called_once_with("erupting volcano", "video")


def test_guided_generate_llm_down_returns_algo_with_guide_injected():
    """When Qwen is offline, guided_generate falls back to algo slug with guide prepended."""
    with patch.object(gp, "_llm_available", return_value=False):
        result = gp.guided_generate("underwater cave exploration", "video")
    assert result["source"] == "algo"
    assert "underwater cave exploration" in result["prompt"]
    assert result["type"] == "video"


def test_guided_generate_llm_returns_none_falls_back():
    """If _llm_guided returns None (error), guided_generate falls back to algo."""
    with patch.object(gp, "_llm_available", return_value=True), \
         patch.object(gp, "_llm_guided", return_value=None):
        result = gp.guided_generate("golden hour cliffs", "skyreels")
    assert result["source"] == "algo"
    assert "golden hour cliffs" in result["prompt"]


def test_guided_generate_no_enhance_skips_llm():
    """enhance=False never calls _llm_available or _llm_guided."""
    with patch.object(gp, "_llm_available") as mock_avail, \
         patch.object(gp, "_llm_guided") as mock_guided:
        result = gp.guided_generate("misty mountains", "video", enhance=False)
    mock_avail.assert_not_called()
    mock_guided.assert_not_called()
    assert result["source"] == "algo"
    assert "misty mountains" in result["prompt"]


def test_guided_generate_image_type():
    """guided_generate works with type='image', using image algo fallback."""
    with patch.object(gp, "_llm_available", return_value=False):
        result = gp.guided_generate("sunset over the ocean", "image")
    assert result["type"] == "image"
    assert "sunset over the ocean" in result["prompt"]
    assert result["source"] == "algo"
```

- [ ] **Step 2: Verify the tests fail**

```bash
cd /home/ttuser/code/tt-local-generator
/usr/bin/python3 -m pytest tests/test_generate_prompt_guided.py -v 2>&1 | head -30
```

Expected: all tests fail with `AttributeError: module 'generate_prompt' has no attribute '_llm_guided'`

- [ ] **Step 3: Implement `_llm_guided` and `guided_generate`**

Open `app/generate_prompt.py`. After the `_llm_polish` function (ends around line 304), append:

```python
def _llm_guided(guide: str, prompt_type: str, timeout: int = 45) -> str | None:
    """
    Ask the prompt server to generate a fresh prompt inspired by a guiding theme.

    Unlike _llm_polish (which rewrites an existing slug), this function gives the
    LLM the user's theme string and asks it to produce a complete cinematic prompt
    from scratch.  Returns None on any network or parse error.
    """
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a cinematic prompt writer for AI video generation. "
                    "Write one tight, vivid prompt inspired by the theme below. "
                    "Hard limit: 25 words. No preamble, no quotes, no explanation. "
                    "Never add gore, body horror, graphic violence, or disturbing imagery."
                ),
            },
            {
                "role": "user",
                "content": f"{_TYPE_HINT[prompt_type]}\n\nTheme: {guide}",
            },
        ],
        "max_tokens": 80,
        "temperature": 0.70,
        "top_p": 0.90,
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
        return resp["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError):
        return None


def guided_generate(
    guide: str,
    prompt_type: str = "video",
    enhance: bool = True,
) -> dict:
    """
    Generate one prompt centred on a user-supplied guiding theme.

    When the Qwen prompt server is up and enhance=True, sends the guide to the
    LLM and asks it to write a complete cinematic prompt around that theme.
    Falls back to an algorithmic slug with the guide prepended if the server is
    down or returns an error.

    Returns the same schema as generate():
        {"prompt": str, "type": str, "source": "llm"|"algo", "slug": str}
    """
    if enhance and _llm_available():
        polished = _llm_guided(guide, prompt_type)
        if polished:
            return {
                "prompt": polished,
                "type": prompt_type,
                "source": "llm",
                "slug": guide,
            }

    # Fallback: algo slug with guide prepended so the user's intent is preserved.
    algo_fn = _ALGO_FN.get(prompt_type, _algo_video)
    slug_base, _ = algo_fn()
    slug = f"{guide}; {slug_base}"
    return {
        "prompt": slug,
        "type": prompt_type,
        "source": "algo",
        "slug": slug,
    }
```

- [ ] **Step 4: Verify all guided tests pass**

```bash
/usr/bin/python3 -m pytest tests/test_generate_prompt_guided.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Verify existing tests still pass**

```bash
/usr/bin/python3 -m pytest tests/ -q
```

Expected: all existing tests pass (107+10 = 117 total), no failures.

- [ ] **Step 6: Commit**

```bash
git add app/generate_prompt.py tests/test_generate_prompt_guided.py
git commit -m "feat: add guided_generate() and _llm_guided() to generate_prompt.py"
```

---

## Task 2: `cmd_queue_run` in `tt-ctl`

**Files:**
- Modify: `tt-ctl`
- Create: `tests/test_queue_run.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_queue_run.py`:

```python
"""
Tests for cmd_queue_run() in tt-ctl.

Imports tt-ctl via importlib (it has no .py extension).
All HistoryStore I/O is redirected to tmp_path.
All network calls are mocked.
"""
import importlib.util
import json
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ── Load tt-ctl as a module ───────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

_TTCTL_PATH = Path(__file__).parent.parent / "tt-ctl"
_spec = importlib.util.spec_from_file_location("tt_ctl", _TTCTL_PATH)
tt_ctl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tt_ctl)

# ── Fixtures ──────────────────────────────────────────────────────────────────
import history_store as hs


def _patch_store(monkeypatch, tmp_path):
    """Redirect all HistoryStore paths to tmp_path."""
    monkeypatch.setattr(hs, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(hs, "VIDEOS_DIR", tmp_path)
    monkeypatch.setattr(hs, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(hs, "THUMBNAILS_DIR", tmp_path)
    monkeypatch.setattr(hs, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(hs.HistoryStore, "_QUEUE_FILE", tmp_path / "queue.json")


def _make_item(prompt: str, model_source: str = "video") -> dict:
    return {
        "prompt": prompt,
        "negative_prompt": "",
        "steps": 20,
        "seed": -1,
        "seed_image_path": "",
        "model_source": model_source,
        "guidance_scale": 5.0,
        "ref_video_path": "",
        "ref_char_path": "",
        "animate_mode": "animation",
        "model_id": "",
        "job_id_override": "",
    }


def _make_args(server="http://localhost:8000", dry_run=False):
    args = MagicMock()
    args.server = server
    args.dry_run = dry_run
    return args


# ── Empty queue ───────────────────────────────────────────────────────────────

def test_queue_run_empty_queue_exits_cleanly(monkeypatch, tmp_path):
    """queue run on an empty queue prints a message and returns without error."""
    _patch_store(monkeypatch, tmp_path)
    mock_client = MagicMock()
    with patch.object(tt_ctl, "_make_client", return_value=mock_client):
        tt_ctl.cmd_queue_run(_make_args())
    mock_client.health_check.assert_not_called()


# ── Dry run ───────────────────────────────────────────────────────────────────

def test_queue_run_dry_run_does_not_modify_queue(monkeypatch, tmp_path):
    """--dry-run prints items but does not remove them from queue.json."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"
    items = [_make_item("a red fox"), _make_item("a blue whale")]
    queue_file.write_text(json.dumps(items))

    mock_client = MagicMock()
    with patch.object(tt_ctl, "_make_client", return_value=mock_client):
        tt_ctl.cmd_queue_run(_make_args(dry_run=True))

    # Queue unchanged
    remaining = json.loads(queue_file.read_text())
    assert len(remaining) == 2
    mock_client.health_check.assert_not_called()


# ── Success path ──────────────────────────────────────────────────────────────

def test_queue_run_success_removes_item_from_queue(monkeypatch, tmp_path):
    """A successful generation removes the item from queue.json."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"
    items = [_make_item("a cat sitting")]
    queue_file.write_text(json.dumps(items))

    mock_client = MagicMock()
    mock_client.health_check.return_value = True

    fake_record = MagicMock()
    fake_record.media_file_path = "/tmp/fake.mp4"

    def fake_run_with_callbacks(on_progress, on_finished, on_error):
        on_finished(fake_record)

    mock_worker = MagicMock()
    mock_worker.run_with_callbacks.side_effect = fake_run_with_callbacks

    with patch.object(tt_ctl, "_make_client", return_value=mock_client), \
         patch.object(tt_ctl, "_make_worker_for_item", return_value=mock_worker):
        tt_ctl.cmd_queue_run(_make_args())

    remaining = json.loads(queue_file.read_text())
    assert remaining == []


def test_queue_run_processes_multiple_items_in_order(monkeypatch, tmp_path):
    """Multiple items are consumed in order; all are removed on success."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"
    items = [_make_item("first"), _make_item("second"), _make_item("third")]
    queue_file.write_text(json.dumps(items))

    mock_client = MagicMock()
    mock_client.health_check.return_value = True

    processed_prompts = []

    def fake_make_worker(client, store, item):
        worker = MagicMock()
        _prompt = item["prompt"]

        def run(on_progress, on_finished, on_error):
            processed_prompts.append(_prompt)
            rec = MagicMock()
            rec.media_file_path = f"/tmp/{_prompt}.mp4"
            on_finished(rec)

        worker.run_with_callbacks.side_effect = run
        return worker

    with patch.object(tt_ctl, "_make_client", return_value=mock_client), \
         patch.object(tt_ctl, "_make_worker_for_item", side_effect=fake_make_worker):
        tt_ctl.cmd_queue_run(_make_args())

    assert processed_prompts == ["first", "second", "third"]
    remaining = json.loads(queue_file.read_text())
    assert remaining == []


# ── Failure path ──────────────────────────────────────────────────────────────

def test_queue_run_failure_removes_item_from_queue(monkeypatch, tmp_path):
    """A failed generation (on_error) still removes the item from queue.json."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"
    queue_file.write_text(json.dumps([_make_item("bad prompt")]))

    mock_client = MagicMock()
    mock_client.health_check.return_value = True

    def fail_run(on_progress, on_finished, on_error):
        on_error("Download failed: connection reset")

    mock_worker = MagicMock()
    mock_worker.run_with_callbacks.side_effect = fail_run

    with patch.object(tt_ctl, "_make_client", return_value=mock_client), \
         patch.object(tt_ctl, "_make_worker_for_item", return_value=mock_worker):
        tt_ctl.cmd_queue_run(_make_args())

    remaining = json.loads(queue_file.read_text())
    assert remaining == []


# ── Server offline (skip) ─────────────────────────────────────────────────────

def test_queue_run_offline_skips_item_leaves_in_queue(monkeypatch, tmp_path):
    """If health_check() fails, the item stays in queue.json and is not run."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"
    items = [_make_item("skip me"), _make_item("skip me too")]
    queue_file.write_text(json.dumps(items))

    mock_client = MagicMock()
    mock_client.health_check.return_value = False

    with patch.object(tt_ctl, "_make_client", return_value=mock_client), \
         patch.object(tt_ctl, "_make_worker_for_item") as mock_make:
        tt_ctl.cmd_queue_run(_make_args())

    mock_make.assert_not_called()
    remaining = json.loads(queue_file.read_text())
    assert len(remaining) == 2


def test_queue_run_partial_skip_processes_online_items(monkeypatch, tmp_path):
    """If first item's server is offline but second is online, second runs."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"
    items = [_make_item("skip"), _make_item("run me")]
    queue_file.write_text(json.dumps(items))

    call_count = [0]

    def health_side_effect():
        # First call: offline; subsequent calls: online
        call_count[0] += 1
        return call_count[0] > 1

    mock_client = MagicMock()
    mock_client.health_check.side_effect = health_side_effect

    processed = []

    def fake_make_worker(client, store, item):
        worker = MagicMock()

        def run(on_progress, on_finished, on_error):
            processed.append(item["prompt"])
            rec = MagicMock()
            rec.media_file_path = "/tmp/out.mp4"
            on_finished(rec)

        worker.run_with_callbacks.side_effect = run
        return worker

    with patch.object(tt_ctl, "_make_client", return_value=mock_client), \
         patch.object(tt_ctl, "_make_worker_for_item", side_effect=fake_make_worker):
        tt_ctl.cmd_queue_run(_make_args())

    # Only "run me" was processed
    assert processed == ["run me"]
    # "skip" item stays in queue
    remaining = json.loads(queue_file.read_text())
    assert len(remaining) == 1
    assert remaining[0]["prompt"] == "skip"


# ── Ctrl+C ────────────────────────────────────────────────────────────────────

def test_queue_run_ctrl_c_removes_current_item_leaves_rest(monkeypatch, tmp_path):
    """Ctrl+C removes the in-flight item (submitted to server) and leaves the rest."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"
    items = [_make_item("in-flight"), _make_item("not-yet")]
    queue_file.write_text(json.dumps(items))

    mock_client = MagicMock()
    mock_client.health_check.return_value = True

    mock_worker = MagicMock()
    mock_worker._current_job_id = "deadbeef1234"

    with patch.object(tt_ctl, "_make_client", return_value=mock_client), \
         patch.object(tt_ctl, "_make_worker_for_item", return_value=mock_worker), \
         patch("threading.Event.wait", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as exc:
            tt_ctl.cmd_queue_run(_make_args())

    assert exc.value.code == 1
    remaining = json.loads(queue_file.read_text())
    assert len(remaining) == 1
    assert remaining[0]["prompt"] == "not-yet"


# ── Worker selection ──────────────────────────────────────────────────────────

def test_make_worker_for_item_video_returns_generation_worker():
    """model_source='video' creates a GenerationWorker."""
    client = MagicMock()
    store = MagicMock()
    item = _make_item("a horse galloping", model_source="video")
    worker = tt_ctl._make_worker_for_item(client, store, item)
    assert isinstance(worker, tt_ctl.GenerationWorker)


def test_make_worker_for_item_image_returns_image_worker():
    """model_source='image' creates an ImageGenerationWorker."""
    client = MagicMock()
    store = MagicMock()
    item = _make_item("a red rose", model_source="image")
    worker = tt_ctl._make_worker_for_item(client, store, item)
    assert isinstance(worker, tt_ctl.ImageGenerationWorker)


def test_make_worker_for_item_animate_returns_animate_worker():
    """model_source='animate' creates an AnimateGenerationWorker."""
    client = MagicMock()
    store = MagicMock()
    item = {**_make_item("dance move", model_source="animate"),
            "ref_video_path": "/tmp/motion.mp4",
            "ref_char_path": "/tmp/char.png"}
    worker = tt_ctl._make_worker_for_item(client, store, item)
    assert isinstance(worker, tt_ctl.AnimateGenerationWorker)


def test_make_worker_for_item_skyreels_returns_generation_worker():
    """model_source='skyreels' creates a GenerationWorker (same base class as video)."""
    client = MagicMock()
    store = MagicMock()
    item = _make_item("erupting volcano", model_source="skyreels")
    worker = tt_ctl._make_worker_for_item(client, store, item)
    assert isinstance(worker, tt_ctl.GenerationWorker)
    assert worker._model == "skyreels-v2-df"
```

- [ ] **Step 2: Verify the tests fail**

```bash
/usr/bin/python3 -m pytest tests/test_queue_run.py -v 2>&1 | head -30
```

Expected: all tests fail with `AttributeError: module 'tt_ctl' has no attribute 'cmd_queue_run'` and similar.

- [ ] **Step 3: Add imports to `tt-ctl`**

In `tt-ctl`, find the existing import block (lines 43–46):
```python
from api_client import APIClient          # noqa: E402
from history_store import HistoryStore    # noqa: E402
from worker import GenerationWorker       # noqa: E402
import server_manager as sm              # noqa: E402
```

Replace with:
```python
from api_client import APIClient                                        # noqa: E402
from history_store import HistoryStore                                  # noqa: E402
from worker import (                                                    # noqa: E402
    GenerationWorker,
    ImageGenerationWorker,
    AnimateGenerationWorker,
)
import generate_prompt as gp                                            # noqa: E402
import server_manager as sm                                             # noqa: E402
```

- [ ] **Step 4: Add `_make_worker_for_item` to `tt-ctl`**

Append after the `_age` helper (before `# ── servers ───`):

```python
# ── Worker selection ──────────────────────────────────────────────────────────

# Maps model_source values stored in queue items to the model identifier string
# forwarded to the inference server.
_MODEL_FOR_SRC: dict[str, str] = {
    "video":    "wan2.2-t2v",
    "mochi":    "mochi-1-preview",
    "skyreels": "skyreels-v2-df",
    "image":    "flux.1-dev",
    "animate":  "wan2.2-animate-14b",
}


def _make_worker_for_item(client: "APIClient", store: "HistoryStore", item: dict):
    """
    Instantiate the correct generation worker for a queue item dict.

    Selects GenerationWorker, ImageGenerationWorker, or AnimateGenerationWorker
    based on item["model_source"].  Unknown model_source values default to video.
    """
    src    = item.get("model_source", "video")
    model  = _MODEL_FOR_SRC.get(src, "wan2.2-t2v")
    prompt = item.get("prompt", "")
    neg    = item.get("negative_prompt", "")
    steps  = item.get("steps", 30)
    seed   = item.get("seed", -1)

    if src == "image":
        return ImageGenerationWorker(
            client=client,
            store=store,
            prompt=prompt,
            negative_prompt=neg,
            num_inference_steps=steps,
            seed=seed,
            guidance_scale=item.get("guidance_scale", 3.5),
            model=model,
        )

    if src == "animate":
        return AnimateGenerationWorker(
            client=client,
            store=store,
            reference_video_path=item.get("ref_video_path", ""),
            reference_image_path=item.get("ref_char_path", ""),
            prompt=prompt,
            num_inference_steps=steps,
            seed=seed,
            animate_mode=item.get("animate_mode", "animation"),
            model=model,
        )

    # video / mochi / skyreels → GenerationWorker
    return GenerationWorker(
        client=client,
        store=store,
        prompt=prompt,
        negative_prompt=neg,
        num_inference_steps=steps,
        seed=seed,
        seed_image_path=item.get("seed_image_path", ""),
        model=model,
        num_frames=item.get("num_frames"),
    )
```

- [ ] **Step 5: Add `cmd_queue_run` to `tt-ctl`**

Append after `cmd_queue` (before the `# ── history ───` comment):

```python
# ── queue run ─────────────────────────────────────────────────────────────────

def cmd_queue_run(args):
    """
    Drain and execute the persistent queue (blocking).

    Items are removed from queue.json as they complete (success or failure).
    Server-offline items are skipped and left in the queue for later.
    On KeyboardInterrupt, the in-flight item is removed (it was submitted to the
    server and can be recovered with tt-ctl recover); remaining items stay.
    """
    store  = HistoryStore()
    client = _make_client(args)
    dry_run = getattr(args, "dry_run", False)

    queue = store.load_queue()
    if not queue:
        print(dim("Queue is empty."))
        return

    total = len(queue)
    print(bold(f"Queue: {total} item{'s' if total != 1 else ''}"))

    if dry_run:
        for i, item in enumerate(queue):
            src   = item.get("model_source", "video")
            steps = item.get("steps", "?")
            seed  = item.get("seed", -1)
            short = item.get("prompt", "")[:72]
            print(f"  {teal(f'[{i}]')} {dim(src)}  steps={steps}  seed={seed}")
            print(_wrap(short))
        return

    n_done = n_failed = n_skipped = 0
    # skipped_items: server-offline items preserved in queue after the run.
    skipped_items: list = []

    for idx, item in enumerate(queue):
        src   = item.get("model_source", "video")
        short = item.get("prompt", "")[:60]
        print(f"\n  {teal(f'[{idx+1}/{total}]')} {dim(src)}  {short}")

        if not client.health_check():
            print(yellow("    ○ Server offline — skipping (item stays in queue)"))
            n_skipped += 1
            skipped_items.append(item)
            continue

        worker = _make_worker_for_item(client, store, item)

        done   = threading.Event()
        result: dict = {}

        def on_progress(msg):
            print(dim(f"    {msg}"))

        def on_finished(record, _r=result, _d=done):
            _r["record"] = record
            _d.set()

        def on_error(msg, _r=result, _d=done):
            _r["error"] = msg
            _d.set()

        t = threading.Thread(
            target=worker.run_with_callbacks,
            kwargs=dict(on_progress=on_progress, on_finished=on_finished,
                        on_error=on_error),
            daemon=True,
        )
        t.start()

        try:
            done.wait()
        except KeyboardInterrupt:
            worker.cancel()
            # Current item was submitted to server — remove it from queue.
            # Remaining unprocessed items + any previously skipped items are kept.
            remaining = skipped_items + list(queue[idx + 1:])
            store.save_queue(remaining)
            jid = getattr(worker, "_current_job_id", None) or "unknown"
            jid_short = jid[:8] if jid != "unknown" else jid
            print(yellow(f"\n  Cancelled. Job may still be running on server ({jid_short}…)"))
            print(dim("  Run: tt-ctl recover   to retrieve any completed result"))
            sys.exit(1)

        if "error" in result:
            print(red(f"    ✗ {result['error']}"))
            n_failed += 1
        else:
            record = result["record"]
            print(green("    ✓") + f"  {record.media_file_path}")
            print(dim(f"       {record.duration_s:.0f}s  |  {record.model}"))
            n_done += 1

        # Remove this item from queue.json after each completion (success or fail).
        # skipped_items + everything after current index = what remains.
        store.save_queue(skipped_items + list(queue[idx + 1:]))

    # Restore any server-offline items at their original positions (front of queue).
    store.save_queue(skipped_items)

    print()
    parts = []
    if n_done:    parts.append(green(f"{n_done} done"))
    if n_failed:  parts.append(red(f"{n_failed} failed"))
    if n_skipped: parts.append(yellow(f"{n_skipped} skipped"))
    print("  " + "  ".join(parts) if parts else dim("  Nothing ran."))
```

- [ ] **Step 6: Wire `queue run` into `cmd_queue` and the parser**

In `cmd_queue`, find the `elif sub == "clear":` block and add a new branch before the `else`:

```python
    elif sub == "run":
        cmd_queue_run(args)
```

In `_build_parser`, find `qsub.add_parser("clear", ...)` and after it add:

```python
    qr = qsub.add_parser("run", help="Drain and execute the queue (blocking)")
    qr.add_argument("--dry-run", action="store_true",
                    help="Print what would run without executing")
```

- [ ] **Step 7: Verify all queue-run tests pass**

```bash
/usr/bin/python3 -m pytest tests/test_queue_run.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 8: Verify full suite still passes**

```bash
/usr/bin/python3 -m pytest tests/ -q
```

Expected: all tests pass, no failures.

- [ ] **Step 9: Commit**

```bash
git add tt-ctl tests/test_queue_run.py
git commit -m "feat: add cmd_queue_run and _make_worker_for_item to tt-ctl"
```

---

## Task 3: `cmd_generate` and parser wiring in `tt-ctl`

**Files:**
- Modify: `tt-ctl`
- Create: `tests/test_generate_cmd.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generate_cmd.py`:

```python
"""
Tests for cmd_generate() in tt-ctl.

Covers: prompt generation (guided and free), queue staging, seed increment,
queue-only flag, and auto-run delegation to cmd_queue_run.
"""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

_TTCTL_PATH = Path(__file__).parent.parent / "tt-ctl"
_spec = importlib.util.spec_from_file_location("tt_ctl", _TTCTL_PATH)
tt_ctl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tt_ctl)

import history_store as hs


def _patch_store(monkeypatch, tmp_path):
    monkeypatch.setattr(hs, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(hs, "VIDEOS_DIR", tmp_path)
    monkeypatch.setattr(hs, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(hs, "THUMBNAILS_DIR", tmp_path)
    monkeypatch.setattr(hs, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(hs.HistoryStore, "_QUEUE_FILE", tmp_path / "queue.json")


def _make_args(
    count=1,
    prompt_type="video",
    mode="algo",
    no_enhance=False,
    steps=30,
    seed=-1,
    queue_only=False,
    guide=None,
    server="http://localhost:8000",
):
    args = MagicMock()
    args.count = count
    args.type = prompt_type
    args.mode = mode
    args.no_enhance = no_enhance
    args.steps = steps
    args.seed = seed
    args.queue_only = queue_only
    args.guide = guide
    args.server = server
    args.dry_run = False
    return args


# ── queue-only flag ───────────────────────────────────────────────────────────

def test_generate_queue_only_adds_items_does_not_run(monkeypatch, tmp_path):
    """--queue-only stages items in queue.json without calling cmd_queue_run."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"

    fake_result = {"prompt": "a red fox trots", "type": "video", "source": "algo", "slug": "a red fox trots"}

    with patch.object(tt_ctl.gp, "generate", return_value=fake_result), \
         patch.object(tt_ctl, "cmd_queue_run") as mock_run:
        tt_ctl.cmd_generate(_make_args(count=2, queue_only=True))

    mock_run.assert_not_called()
    items = json.loads(queue_file.read_text())
    assert len(items) == 2
    assert all(i["prompt"] == "a red fox trots" for i in items)


def test_generate_without_queue_only_calls_cmd_queue_run(monkeypatch, tmp_path):
    """Without --queue-only, cmd_generate calls cmd_queue_run after staging."""
    _patch_store(monkeypatch, tmp_path)

    fake_result = {"prompt": "misty cliffs", "type": "video", "source": "algo", "slug": "misty cliffs"}

    with patch.object(tt_ctl.gp, "generate", return_value=fake_result), \
         patch.object(tt_ctl, "cmd_queue_run") as mock_run:
        tt_ctl.cmd_generate(_make_args(count=1, queue_only=False))

    mock_run.assert_called_once()


# ── seed increment ────────────────────────────────────────────────────────────

def test_generate_explicit_seed_increments_per_item(monkeypatch, tmp_path):
    """With --seed S and --count N, items get seeds S, S+1, S+2, …"""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"

    fake_result = {"prompt": "ocean waves", "type": "video", "source": "algo", "slug": "ocean waves"}

    with patch.object(tt_ctl.gp, "generate", return_value=fake_result), \
         patch.object(tt_ctl, "cmd_queue_run"):
        tt_ctl.cmd_generate(_make_args(count=3, seed=100))

    items = json.loads(queue_file.read_text())
    assert [i["seed"] for i in items] == [100, 101, 102]


def test_generate_random_seed_stays_minus_one(monkeypatch, tmp_path):
    """With --seed -1 (random), all items keep seed=-1."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"

    fake_result = {"prompt": "x", "type": "video", "source": "algo", "slug": "x"}

    with patch.object(tt_ctl.gp, "generate", return_value=fake_result), \
         patch.object(tt_ctl, "cmd_queue_run"):
        tt_ctl.cmd_generate(_make_args(count=3, seed=-1))

    items = json.loads(queue_file.read_text())
    assert all(i["seed"] == -1 for i in items)


# ── guided vs free generation ─────────────────────────────────────────────────

def test_generate_with_guide_calls_guided_generate(monkeypatch, tmp_path):
    """When guide is set, cmd_generate calls gp.guided_generate (not gp.generate)."""
    _patch_store(monkeypatch, tmp_path)

    guided_result = {"prompt": "volcano at dusk", "type": "video", "source": "llm", "slug": "volcano theme"}

    with patch.object(tt_ctl.gp, "guided_generate", return_value=guided_result) as mock_guided, \
         patch.object(tt_ctl.gp, "generate") as mock_free, \
         patch.object(tt_ctl, "cmd_queue_run"):
        tt_ctl.cmd_generate(_make_args(count=2, guide="volcano theme"))

    assert mock_guided.call_count == 2
    mock_free.assert_not_called()
    # verify guide and enhance are passed correctly
    mock_guided.assert_called_with("volcano theme", "video", enhance=True)


def test_generate_without_guide_calls_generate(monkeypatch, tmp_path):
    """When no guide, cmd_generate calls gp.generate (not gp.guided_generate)."""
    _patch_store(monkeypatch, tmp_path)

    free_result = {"prompt": "a fox in snow", "type": "video", "source": "algo", "slug": "..."}

    with patch.object(tt_ctl.gp, "generate", return_value=free_result) as mock_free, \
         patch.object(tt_ctl.gp, "guided_generate") as mock_guided, \
         patch.object(tt_ctl, "cmd_queue_run"):
        tt_ctl.cmd_generate(_make_args(count=1, guide=None))

    mock_free.assert_called_once()
    mock_guided.assert_not_called()


def test_generate_no_enhance_flag_passed_through(monkeypatch, tmp_path):
    """--no-enhance is forwarded to gp.generate as enhance=False."""
    _patch_store(monkeypatch, tmp_path)

    free_result = {"prompt": "p", "type": "video", "source": "algo", "slug": "p"}

    with patch.object(tt_ctl.gp, "generate", return_value=free_result) as mock_free, \
         patch.object(tt_ctl, "cmd_queue_run"):
        tt_ctl.cmd_generate(_make_args(no_enhance=True))

    _, kwargs = mock_free.call_args
    assert kwargs.get("enhance") is False


# ── model_source in staged items ──────────────────────────────────────────────

def test_generate_sets_model_source_from_type(monkeypatch, tmp_path):
    """Items staged in queue.json have model_source matching --type."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"

    skyreels_result = {"prompt": "crater lake", "type": "skyreels", "source": "algo", "slug": "crater lake"}

    with patch.object(tt_ctl.gp, "generate", return_value=skyreels_result), \
         patch.object(tt_ctl, "cmd_queue_run"):
        tt_ctl.cmd_generate(_make_args(count=1, prompt_type="skyreels"))

    items = json.loads(queue_file.read_text())
    assert items[0]["model_source"] == "skyreels"


# ── existing queue preserved ──────────────────────────────────────────────────

def test_generate_appends_to_existing_queue(monkeypatch, tmp_path):
    """cmd_generate appends new items after any items already in queue.json."""
    _patch_store(monkeypatch, tmp_path)
    queue_file = tmp_path / "queue.json"

    existing = [{"prompt": "pre-existing", "negative_prompt": "", "steps": 20,
                 "seed": -1, "seed_image_path": "", "model_source": "video",
                 "guidance_scale": 5.0, "ref_video_path": "", "ref_char_path": "",
                 "animate_mode": "animation", "model_id": "", "job_id_override": ""}]
    queue_file.write_text(json.dumps(existing))

    new_result = {"prompt": "new item", "type": "video", "source": "algo", "slug": "new item"}

    with patch.object(tt_ctl.gp, "generate", return_value=new_result), \
         patch.object(tt_ctl, "cmd_queue_run"):
        tt_ctl.cmd_generate(_make_args(count=1, queue_only=True))

    items = json.loads(queue_file.read_text())
    assert len(items) == 2
    assert items[0]["prompt"] == "pre-existing"
    assert items[1]["prompt"] == "new item"
```

- [ ] **Step 2: Verify the tests fail**

```bash
/usr/bin/python3 -m pytest tests/test_generate_cmd.py -v 2>&1 | head -30
```

Expected: all tests fail with `AttributeError: module 'tt_ctl' has no attribute 'cmd_generate'`.

- [ ] **Step 3: Implement `cmd_generate` in `tt-ctl`**

Append after `cmd_queue_run` (before `# ── history ───`):

```python
# ── generate ──────────────────────────────────────────────────────────────────

def cmd_generate(args):
    """
    Generate N prompts (optionally guided by a theme) and run them through the queue.

    Prompts are written to queue.json first, then cmd_queue_run drains the queue
    unless --queue-only is set.  With an explicit --seed S and --count N, seeds
    are assigned as S, S+1, S+2, … so each generation gets a unique seed.
    """
    guide      = getattr(args, "guide", None)
    count      = getattr(args, "count", 1)
    ptype      = getattr(args, "type", "video")
    mode       = getattr(args, "mode", "algo")
    enhance    = not getattr(args, "no_enhance", False)
    steps      = getattr(args, "steps", 30)
    seed       = getattr(args, "seed", -1)
    queue_only = getattr(args, "queue_only", False)

    store          = HistoryStore()
    existing_queue = store.load_queue()

    # Warn once at the start if LLM polish / guided generation was requested but
    # the Qwen server is not available, so the user knows the fallback is active.
    if enhance:
        if not gp._llm_available():
            print(yellow("  Qwen server offline — algo fallback active"))

    print(bold(f"Generating {count} prompt{'s' if count != 1 else ''}…"))

    new_items = []
    for i in range(count):
        item_seed = (seed + i) if seed >= 0 else -1

        if guide:
            result = gp.guided_generate(guide, ptype, enhance=enhance)
        else:
            result = gp.generate(prompt_type=ptype, mode=mode, enhance=enhance)

        prompt = result["prompt"]
        source = result["source"]
        short  = prompt[:70] + ("…" if len(prompt) > 70 else "")
        print(f"  {dim(f'[{i+1}/{count}]')} {dim(source)}  {short}")

        new_items.append({
            "prompt":          prompt,
            "negative_prompt": "",
            "steps":           steps,
            "seed":            item_seed,
            "seed_image_path": "",
            "model_source":    ptype,
            "guidance_scale":  5.0,
            "ref_video_path":  "",
            "ref_char_path":   "",
            "animate_mode":    "animation",
            "model_id":        "",
            "job_id_override": "",
        })

    store.save_queue(existing_queue + new_items)
    print(green("✓") + f"  {count} item{'s' if count != 1 else ''} added to queue")

    if queue_only:
        print(dim("  Run: tt-ctl queue run   to start generation"))
        return

    cmd_queue_run(args)
```

- [ ] **Step 4: Wire `generate` into the parser and dispatch**

In `_build_parser`, append a new subparser after the `run` subparser block:

```python
    # generate
    gen = sub.add_parser(
        "generate",
        help="Generate prompts (optionally guided) and run them",
    )
    gen.add_argument(
        "guide", nargs="?", default=None, metavar="GUIDE",
        help="Optional guiding theme — Qwen generates around it if available",
    )
    gen.add_argument("--count", type=int, default=1, metavar="N",
                     help="Number of prompts to generate (default: 1)")
    gen.add_argument(
        "--type", default="video",
        choices=["video", "image", "skyreels", "animate"],
        metavar="TYPE",
        help="Model type: video|image|skyreels|animate (default: video)",
    )
    gen.add_argument(
        "--mode", default="algo", choices=["algo", "markov"],
        help="Base generation mode (default: algo; ignored when GUIDE + Qwen up)",
    )
    gen.add_argument(
        "--no-enhance", action="store_true",
        help="Skip Qwen polish / guided generation even if server is up",
    )
    gen.add_argument("--steps", type=int, default=30,
                     help="Inference steps per generation (default: 30)")
    gen.add_argument("--seed", type=int, default=-1,
                     help="Starting seed (-1 = random). With --count N, seeds are S, S+1, …")
    gen.add_argument("--queue-only", action="store_true",
                     help="Stage prompts in queue.json but do not run them")
```

In `main`, add `"generate": cmd_generate` to the dispatch dict:

```python
    dispatch = {
        "status":   cmd_status,
        "servers":  cmd_servers,
        "start":    cmd_start,
        "stop":     cmd_stop,
        "restart":  cmd_restart,
        "queue":    cmd_queue,
        "history":  cmd_history,
        "server":   cmd_server,
        "recover":  cmd_recover,
        "run":      cmd_run,
        "generate": cmd_generate,
    }
```

- [ ] **Step 5: Verify all generate-cmd tests pass**

```bash
/usr/bin/python3 -m pytest tests/test_generate_cmd.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 6: Verify full suite passes**

```bash
/usr/bin/python3 -m pytest tests/ -q
```

Expected: all tests pass (≥ 127 total), no failures.

- [ ] **Step 7: Commit**

```bash
git add tt-ctl tests/test_generate_cmd.py
git commit -m "feat: add cmd_generate and tt-ctl generate subcommand"
```

---

## Task 4: Update `CLAUDE.md` and smoke-test the CLI

**Files:**
- Modify: `CLAUDE.md` (project-level, at repo root)

- [ ] **Step 1: Add new commands to CLAUDE.md**

In `CLAUDE.md`, find the existing `tt-ctl` documentation block and append to it:

```markdown
    tt-ctl queue run               Drain and execute the queue (blocking)
                                   Flags: --dry-run
    tt-ctl generate ["GUIDE"]      Generate N prompts and run them
                                   Flags: --count N  --type video|image|skyreels|animate
                                          --mode algo|markov  --no-enhance
                                          --steps N  --seed S  --queue-only
                                          --server URL
```

- [ ] **Step 2: Smoke-test the parser (no server needed)**

```bash
cd /home/ttuser/code/tt-local-generator
./tt-ctl generate --help
```

Expected output includes `GUIDE`, `--count`, `--type`, `--queue-only`.

```bash
./tt-ctl queue run --help
```

Expected output includes `--dry-run`.

```bash
./tt-ctl queue run --dry-run
```

Expected: `Queue is empty.` (since queue is empty after tests cleared it).

- [ ] **Step 3: Smoke-test generate --queue-only (no server needed)**

```bash
./tt-ctl generate --count 2 --type video --queue-only --no-enhance
```

Expected: prints 2 algo-generated prompts, `✓  2 items added to queue`, then `Run: tt-ctl queue run`.

```bash
./tt-ctl queue
```

Expected: lists 2 items matching the generated prompts.

```bash
./tt-ctl queue clear
```

Expected: `✓  Cleared 2 item(s) from queue`.

- [ ] **Step 4: Smoke-test guided generate --queue-only**

```bash
./tt-ctl generate --count 1 --queue-only --no-enhance "coastal fog through redwood forest"
```

Expected: prompt contains `coastal fog through redwood forest`, added to queue.

```bash
./tt-ctl queue
./tt-ctl queue clear
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document tt-ctl queue run and generate commands in CLAUDE.md"
```

---

## Done

After Task 4, the full pipeline works headlessly:

```bash
tt-ctl start wan2.2
tt-ctl generate --count 5 "coastal fog rolling through redwood forest"
# streams progress for each video …
# open GUI → all 5 videos appear in history with thumbnails and metadata
```
