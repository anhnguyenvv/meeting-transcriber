"""
config.py — Central configuration loader.
Reads .env, detects OS, and exposes typed constants used across the project.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env if present ──────────────────────────────────────────────────────
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# ── OS detection ──────────────────────────────────────────────────────────────
IS_MAC: bool = platform.system() == "Darwin"
IS_WIN: bool = platform.system() == "Windows"
IS_LINUX: bool = platform.system() == "Linux"

# Hint to pre-select the loopback device in the device picker
LOOPBACK_DEVICE_HINT: str = "BlackHole 2ch" if IS_MAC else "CABLE Output"

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "small")
JAPANESE_ASR_MODEL: str = os.getenv("JAPANESE_ASR_MODEL", "kotoba-tech/kotoba-whisper-v2.0-faster")
# Supported language codes for faster-whisper auto-detect output
SUPPORTED_LANGS: set[str] = {"ja", "en", "vi"}
SAMPLE_RATE: int = 16_000  # Hz — required by Whisper

# ── Pyannote diarization ──────────────────────────────────────────────────────
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Model profiles theo dung lượng RAM:
#   qwen2.5:1.5b  — ~1 GB   | RAM 4-6 GB  | nhanh, đủ dùng
#   qwen2.5:3b    — ~1.9 GB | RAM 8 GB    | cân bằng tốt  ← MẶC ĐỊNH
#   qwen2.5:7b-instruct — ~4.7 GB | RAM 16+ GB | tốt nhất
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Chunk size (in characters) for translation — keeps each Ollama request fast
TRANSLATION_CHUNK_CHARS: int = 4_000
TRANSLATION_OVERLAP_CHARS: int = 200

# ── Multilingual / code-switching ─────────────────────────────────────────────
# Per-chunk language detection: improves accuracy for meetings mixing JA/EN/VI
MULTILINGUAL_CHUNK_S: float = float(os.getenv("MULTILINGUAL_CHUNK_S", "30"))

# ── Live transcription ───────────────────────────────────────────────────────
LIVE_CHUNK_DURATION_S: float = float(os.getenv("LIVE_CHUNK_S", "5"))
LIVE_OVERLAP_S: float = float(os.getenv("LIVE_OVERLAP_S", "1.5"))
LIVE_SILENCE_THRESHOLD: float = float(os.getenv("LIVE_SILENCE_THRESHOLD", "0.001"))
