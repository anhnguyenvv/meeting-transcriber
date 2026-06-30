"""
test_pipeline.py — End-to-end smoke tests.

Usage:
    # Install test deps first (already in requirements.txt)
    pip install pytest

    # Run all tests (skips any that lack sample files or Ollama)
    pytest tests/ -v

    # Run only the align unit test (no model needed)
    pytest tests/test_pipeline.py::test_align_merge -v

Sample files:
    Put short WAV clips (≤30 s, 16kHz mono) in tests/samples/:
        sample_en.wav    — English
        sample_ja.wav    — Japanese
        sample_vi.wav    — Vietnamese
        sample_mixed.wav — 2 speakers, mixed JA/EN
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAMPLES_DIR = Path(__file__).parent / "samples"


# ── Helpers ───────────────────────────────────────────────────────────────────

def sample(name: str) -> Path:
    return SAMPLES_DIR / name


def has_sample(name: str) -> bool:
    return sample(name).exists()


def ollama_available() -> bool:
    try:
        from src.ollama_client import is_ollama_available
        return is_ollama_available()
    except Exception:
        return False


def hf_token_set() -> bool:
    from src.config import HF_TOKEN
    return bool(HF_TOKEN)


# ── Unit tests (no models needed) ────────────────────────────────────────────

class TestAlign:
    """Pure-function tests for align.py — no ML models required."""

    def test_align_merge_basic(self):
        from src.transcribe import TranscriptSegment
        from src.diarize import SpeakerTurn
        from src import align

        segments = [
            TranscriptSegment(0.0, 3.0, "Hello world.", "en"),
            TranscriptSegment(3.5, 6.0, "This is a test.", "en"),
            TranscriptSegment(7.0, 10.0, "Goodbye.", "en"),
        ]
        turns = [
            SpeakerTurn("Speaker 1", 0.0, 5.0),
            SpeakerTurn("Speaker 2", 5.5, 11.0),
        ]
        lines = align.merge(segments, turns)
        # First two segments → Speaker 1, last → Speaker 2
        assert lines[0].speaker == "Speaker 1"
        assert lines[-1].speaker == "Speaker 2"
        assert len(lines) == 2  # collapsed

    def test_align_merge_no_turns(self):
        from src.transcribe import TranscriptSegment
        from src import align

        segments = [TranscriptSegment(0.0, 2.0, "Hi.", "vi")]
        lines = align.merge(segments, [])
        assert len(lines) == 1
        assert lines[0].speaker == "Speaker 1"

    def test_align_to_text_format(self):
        from src.transcribe import TranscriptSegment
        from src import align

        segments = [TranscriptSegment(65.0, 70.0, "Testing.", "en")]
        lines = align.merge(segments, [])
        text = align.to_text(lines)
        assert "01:05" in text   # 65 s = 1m 05s
        assert "Speaker 1" in text
        assert "Testing." in text

    def test_collapse_consecutive_speakers(self):
        from src.transcribe import TranscriptSegment
        from src.diarize import SpeakerTurn
        from src import align

        segments = [
            TranscriptSegment(0.0, 2.0, "One.", "en"),
            TranscriptSegment(2.1, 4.0, "Two.", "en"),
            TranscriptSegment(4.1, 6.0, "Three.", "en"),
        ]
        turns = [SpeakerTurn("Speaker 1", 0.0, 6.0)]
        lines = align.merge(segments, turns)
        assert len(lines) == 1
        assert "One." in lines[0].text
        assert "Two." in lines[0].text


class TestConvert:
    """Audio conversion — only checks ffmpeg is accessible."""

    def test_ffmpeg_available(self):
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        assert Path(exe).exists(), f"ffmpeg not found at {exe}"


class TestConfig:
    def test_config_loads(self):
        from src import config
        assert config.SAMPLE_RATE == 16000
        assert config.WHISPER_MODEL in ("tiny", "base", "small", "medium", "large-v2", "large-v3")


# ── Integration tests (require sample WAVs + Ollama) ─────────────────────────

@pytest.mark.skipif(not has_sample("sample_en.wav"), reason="sample_en.wav not found in tests/samples/")
@pytest.mark.skipif(not ollama_available(), reason="Ollama not running or model not available")
class TestEnglishFile:
    def test_transcribe_en(self):
        from src import transcribe
        segs = transcribe.run(sample("sample_en.wav"))
        assert len(segs) > 0
        assert segs[0].language == "en"
        assert any(seg.text.strip() for seg in segs)

    def test_translate_en(self):
        from src import translate
        result = translate.to_vi("Speaker 1 [00:01 → 00:03]: Hello, how are you?")
        assert len(result) > 0
        # Should contain Vietnamese characters or at least a non-empty string
        assert isinstance(result, str)

    def test_summarize_en(self):
        from src import summarize
        result = summarize.to_vi("Speaker 1: We decided to launch in Q3.\nSpeaker 2: Agreed, budget is approved.")
        assert "Tóm tắt" in result or len(result) > 50


@pytest.mark.skipif(not has_sample("sample_ja.wav"), reason="sample_ja.wav not found in tests/samples/")
@pytest.mark.skipif(not ollama_available(), reason="Ollama not running or model not available")
class TestJapaneseFile:
    def test_transcribe_ja(self):
        from src import transcribe
        segs = transcribe.run(sample("sample_ja.wav"))
        assert len(segs) > 0
        assert segs[0].language == "ja"


@pytest.mark.skipif(not has_sample("sample_vi.wav"), reason="sample_vi.wav not found in tests/samples/")
@pytest.mark.skipif(not ollama_available(), reason="Ollama not running or model not available")
class TestVietnameseFile:
    def test_transcribe_vi(self):
        from src import transcribe
        segs = transcribe.run(sample("sample_vi.wav"))
        assert len(segs) > 0
        assert segs[0].language == "vi"


@pytest.mark.skipif(not has_sample("sample_en.wav"), reason="sample_en.wav not found")
@pytest.mark.skipif(not ollama_available(), reason="Ollama not running")
class TestFullPipeline:
    """End-to-end pipeline test — skips diarization to avoid HF_TOKEN requirement."""

    def test_pipeline_no_diarization(self, tmp_path):
        from src import pipeline

        result = pipeline.run(
            audio_path=sample("sample_en.wav"),
            title="test_run",
            skip_diarization=True,
        )
        assert result.transcript_original
        assert result.transcript_vi
        assert result.summary_vi
        assert result.output_dir.exists()
        assert (result.output_dir / "transcript_original.txt").exists()
        assert (result.output_dir / "summary_vi.md").exists()
        assert result.language == "en"
        assert result.speaker_count >= 1
