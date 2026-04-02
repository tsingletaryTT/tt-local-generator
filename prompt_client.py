#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
"""
Lightweight HTTP client for the tt-prompt-gen server (port 8001).

The server exposes an OpenAI-compatible chat API powered by Qwen3-0.6B on CPU.
This module has no GTK dependencies and is safe to import without a display.

Functions:
    check_health(base_url) -> bool
    generate_prompt(source, seed_text, system_prompt, base_url, max_tokens) -> str
"""
import requests

_DEFAULT_URL = "http://127.0.0.1:8001"


def check_health(base_url: str = _DEFAULT_URL) -> bool:
    """
    Return True if the prompt gen server is up and the model is loaded.

    Calls GET /health and checks the model_ready field.  Returns False on
    any network error, non-200 status, or missing model_ready field.
    """
    try:
        resp = requests.get(f"{base_url}/health", timeout=3)
        if resp.status_code == 200:
            return bool(resp.json().get("model_ready"))
        return False
    except (requests.RequestException, ValueError):
        return False


def generate_prompt(
    source: str,
    seed_text: str,
    system_prompt: str,
    base_url: str = _DEFAULT_URL,
    max_tokens: int = 150,
) -> str:
    """
    Generate a cinematic prompt via the Qwen3-0.6B server.

    Args:
        source:        "video", "image", or "animate" — prefixed to the user
                       message so the model knows which output format to use.
        seed_text:     Existing prompt text to use as a creative seed.  Pass ""
                       to let the model invent freely from its word banks.
        system_prompt: Full contents of prompts/prompt_generator.md.
        base_url:      URL of the prompt gen server (default: http://127.0.0.1:8001).
        max_tokens:    Maximum tokens to generate (default: 150).

    Returns:
        The generated prompt string stripped of leading/trailing whitespace.

    Raises:
        requests.RequestException: On network or HTTP errors.
        ValueError: If the server returns no choices or empty content.
    """
    user_content = f"{source}: {seed_text}"
    payload = {
        "model": "Qwen/Qwen3-0.6B",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8,
        "top_p": 0.9,
    }
    resp = requests.post(
        f"{base_url}/v1/chat/completions",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ValueError(f"No choices in server response: {data}")
    content = choices[0].get("message", {}).get("content", "").strip()
    if not content:
        raise ValueError(f"Empty content in server response: {data}")
    return content
