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


def test_guided_generate_slug_is_guide_when_llm_up():
    """When LLM is used, slug is the raw guide string (not the algo-generated slug)."""
    polished = "Dense fog rolls through redwood forest at dawn"
    with patch.object(gp, "_llm_available", return_value=True), \
         patch.object(gp, "_llm_guided", return_value=polished):
        result = gp.guided_generate("coastal fog redwood", "video")
    assert result["slug"] == "coastal fog redwood"
