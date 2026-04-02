"""Tests for prompt_client — mocked HTTP, no real server needed."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import requests

import prompt_client


def test_check_health_true_when_model_ready():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "model_ready": True}
    with patch("prompt_client.requests.get", return_value=mock_resp):
        assert prompt_client.check_health() is True


def test_check_health_false_when_model_not_ready():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "model_ready": False}
    with patch("prompt_client.requests.get", return_value=mock_resp):
        assert prompt_client.check_health() is False


def test_check_health_false_on_network_error():
    with patch("prompt_client.requests.get", side_effect=requests.ConnectionError()):
        assert prompt_client.check_health() is False


def test_check_health_false_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("prompt_client.requests.get", return_value=mock_resp):
        assert prompt_client.check_health() is False


def _mock_chat_response(content: str):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_generate_prompt_returns_content():
    expected = "A red fox trots through deep snow at midnight"
    with patch("prompt_client.requests.post", return_value=_mock_chat_response(expected)):
        result = prompt_client.generate_prompt("video", "fox in snow", "sys prompt")
    assert result == expected


def test_generate_prompt_strips_whitespace():
    with patch("prompt_client.requests.post", return_value=_mock_chat_response("  hello  ")):
        result = prompt_client.generate_prompt("image", "", "sys")
    assert result == "hello"


def test_generate_prompt_uses_source_prefix():
    captured = {}

    def mock_post(url, json=None, **kwargs):
        captured["json"] = json
        return _mock_chat_response("result")

    with patch("prompt_client.requests.post", side_effect=mock_post):
        prompt_client.generate_prompt("image", "portrait", "sys")

    user_msg = next(m for m in captured["json"]["messages"] if m["role"] == "user")
    assert user_msg["content"].startswith("image:")


def test_generate_prompt_raises_on_empty_content():
    with patch("prompt_client.requests.post", return_value=_mock_chat_response("")):
        with pytest.raises(ValueError, match="Empty content"):
            prompt_client.generate_prompt("video", "", "sys")


def test_generate_prompt_raises_on_no_choices():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"choices": []}
    mock_resp.raise_for_status = MagicMock()
    with patch("prompt_client.requests.post", return_value=mock_resp):
        with pytest.raises(ValueError, match="No choices"):
            prompt_client.generate_prompt("video", "", "sys")
