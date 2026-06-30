"""
ollama_client.py — Thin wrapper around the Ollama HTTP API.
Shared by translate.py and summarize.py.
"""
from __future__ import annotations

import json
import logging
from typing import Iterator

import requests

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)


def chat(
    system_prompt: str,
    user_message: str,
    model: str = OLLAMA_MODEL,
    stream: bool = False,
) -> str:
    """
    Send a chat request to Ollama and return the full assistant response.

    Parameters
    ----------
    system_prompt : system message (role / instructions)
    user_message  : the actual content to process
    model         : Ollama model name
    stream        : whether to stream (currently reads full response either way)

    Returns
    -------
    str — the assistant's reply text.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,   # low temp for factual translation / summary
            "num_predict": 8192,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running: `ollama serve`"
        )
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP error: {e}\n{resp.text}")

    data = resp.json()
    return data["message"]["content"]


def is_ollama_available() -> bool:
    """Return True if Ollama is reachable and the model is available."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        tags = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in tags]
        # Accept if any listed name starts with our model name (ignores tag variants)
        return any(OLLAMA_MODEL.split(":")[0] in n for n in model_names)
    except Exception:
        return False
