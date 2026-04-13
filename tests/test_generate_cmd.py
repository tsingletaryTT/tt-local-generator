"""
Tests for cmd_generate() in tt-ctl.

Covers: prompt generation (guided and free), queue staging, seed increment,
queue-only flag, and auto-run delegation to cmd_queue_run.
"""
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

# ── Load tt-ctl as a module ───────────────────────────────────────────────────
# importlib.util.spec_from_file_location cannot infer the loader for files
# without a .py extension.  Provide SourceFileLoader explicitly.
_TTCTL_PATH = Path(__file__).parent.parent / "tt-ctl"
_loader = importlib.machinery.SourceFileLoader("tt_ctl", str(_TTCTL_PATH))
_spec = importlib.util.spec_from_loader("tt_ctl", _loader)
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
