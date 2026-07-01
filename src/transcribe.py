"""
transcribe.py — faster-whisper wrapper.

Returns a list of TranscriptSegment objects with timestamps, text, and
detected language. Language is auto-detected per file (not forced), so
Japanese / English / Vietnamese files all work without configuration.

run_multilingual() improves code-switching accuracy by detecting language
per ~30 s chunk independently.
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
import soundfile as sf

from src.config import WHISPER_MODEL, JAPANESE_ASR_MODEL, MULTILINGUAL_CHUNK_S, SAMPLE_RATE

logger = logging.getLogger(__name__)

SUPPORTED_LANGS = {"en", "vi", "ja"}

# Lazy-loaded models (loaded once, reused)
_models = {}


def _get_model(lang: Optional[str] = None):
    model_name = JAPANESE_ASR_MODEL if lang == "ja" else WHISPER_MODEL
    if model_name not in _models:
        logger.info("Loading Whisper model '%s' …", model_name)
        try:
            import torch
            from faster_whisper import WhisperModel

            device = "cuda" if torch.cuda.is_available() else "cpu"
            # int8_float16 on CUDA, int8 on CPU (good for Apple Silicon too)
            compute_type = "int8_float16" if device == "cuda" else "int8"
            logger.info("Using device=%s, compute_type=%s", device, compute_type)
            _models[model_name] = WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {e}") from e
    return _models[model_name]


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class TranscriptSegment:
    start: float       # seconds
    end: float         # seconds
    text: str
    language: str      # detected language code, e.g. "ja", "en", "vi"

    def to_srt_block(self, index: int) -> str:
        def fmt(s: float) -> str:
            h, rem = divmod(int(s), 3600)
            m, sec = divmod(rem, 60)
            ms = int((s - int(s)) * 1000)
            return f"{h:02}:{m:02}:{sec:02},{ms:03}"

        return f"{index}\n{fmt(self.start)} --> {fmt(self.end)}\n{self.text.strip()}\n"


# ── Single-language run (legacy, kept for compatibility) ──────────────────────

def run(
    audio_path: str | Path,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[TranscriptSegment]:
    """
    Transcribe *audio_path* (must be 16 kHz mono WAV).
    Language is auto-detected once for the whole file.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    model = _get_model()

    if progress_cb:
        progress_cb("🎙️ Đang nhận dạng giọng nói (Whisper) …")

    segments_iter, info = model.transcribe(
        str(audio_path),
        language=None,          # auto-detect
        task="transcribe",      # keep original language (not translate to EN)
        vad_filter=True,        # skip silence
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=5,
        word_timestamps=False,
    )

    detected_lang = info.language
    logger.info("Detected language: %s (prob=%.2f)", detected_lang, info.language_probability)

    segments: List[TranscriptSegment] = []
    for seg in segments_iter:
        segments.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                language=detected_lang,
            )
        )

    if progress_cb:
        progress_cb(f"✅ Nhận dạng xong — {len(segments)} đoạn, ngôn ngữ: {detected_lang}")

    return segments


# ── Per-chunk multilingual run ────────────────────────────────────────────────

def _detect_language(model, audio_array: np.ndarray) -> tuple[str, float]:
    """Detect language from a short audio array using Whisper's fast language detection."""
    try:
        # Use native detect_language on the raw array (avoids file I/O and full decode pass)
        lang, prob, all_probs_dict = model.detect_language(audio_array)
        
        # Filter only supported languages to avoid hallucinated rare languages
        if all_probs_dict:
            # all_probs_dict is a list of tuples (lang_code, prob) if returning from detect_language, 
            # or a list of Language (code, probability) namedtuples. 
            # We'll handle it generically as attributes or tuples:
            supported_probs = []
            for item in all_probs_dict:
                lang_code = item[0] if isinstance(item, tuple) else getattr(item, 'language', item[0])
                p = item[1] if isinstance(item, tuple) else getattr(item, 'probability', item[1])
                if lang_code in SUPPORTED_LANGS:
                    supported_probs.append((lang_code, p))
                    
            if supported_probs:
                best_lang, best_prob = max(supported_probs, key=lambda x: x[1])
                return best_lang, best_prob
                
        return lang, prob
    except Exception as e:
        logger.warning(f"Fast language detection failed: {e}. Defaulting to 'vi'.")
        return "vi", 0.0


def run_multilingual(
    audio_path: str | Path,
    chunk_duration_s: float = MULTILINGUAL_CHUNK_S,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[TranscriptSegment]:
    """
    Transcribe with per-chunk language detection for code-switching meetings.

    Splits the audio into chunks of *chunk_duration_s* seconds, detects
    language independently for each chunk, then transcribes with the
    detected language forced — giving much better accuracy when speakers
    switch between JA / EN / VI within the same meeting.

    Parameters
    ----------
    audio_path       : path to the 16 kHz mono WAV.
    chunk_duration_s : chunk size in seconds for language detection (default 30).
    progress_cb      : optional progress callback.

    Returns
    -------
    List of TranscriptSegment ordered by start time, each tagged with its
    detected language.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    default_model = _get_model() # Load default model for language detection

    if progress_cb:
        progress_cb("🎙️ Đang nhận dạng đa ngôn ngữ (per-chunk) …")

    # Read the full audio
    audio_data, sr = sf.read(str(audio_path), dtype="float32")
    if sr != SAMPLE_RATE:
        logger.warning("Audio sample rate %d != expected %d, results may vary", sr, SAMPLE_RATE)

    total_samples = len(audio_data)
    chunk_samples = int(chunk_duration_s * sr)
    total_duration = total_samples / sr

    # Split into chunks
    chunks: list[tuple[int, int]] = []  # (start_sample, end_sample)
    pos = 0
    while pos < total_samples:
        end = min(pos + chunk_samples, total_samples)
        # Skip very short trailing chunks (< 1s)
        if (end - pos) / sr >= 1.0:
            chunks.append((pos, end))
        pos = end

    logger.info("Split %.1fs audio into %d chunks of ~%.0fs each",
                total_duration, len(chunks), chunk_duration_s)

    all_segments: List[TranscriptSegment] = []

    for i, (start_sample, end_sample) in enumerate(chunks):
        chunk_audio = audio_data[start_sample:end_sample]
        chunk_offset = start_sample / sr  # seconds offset from file start

        # Detect language for this chunk
        lang, prob = _detect_language(default_model, chunk_audio)
        if progress_cb:
            progress_cb(
                f"🌐 Chunk {i+1}/{len(chunks)}: ngôn ngữ={lang} (p={prob:.2f})"
            )
        logger.info("Chunk %d/%d: lang=%s (prob=%.2f), offset=%.1fs",
                     i + 1, len(chunks), lang, prob, chunk_offset)

        # Use specific model based on detected language
        model = _get_model(lang)

        try:
            segments_iter, _ = model.transcribe(
                chunk_audio,
                language=lang,       # force detected language
                task="transcribe",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                beam_size=5,
                word_timestamps=False,
            )

            for seg in segments_iter:
                all_segments.append(
                    TranscriptSegment(
                        start=seg.start + chunk_offset,
                        end=seg.end + chunk_offset,
                        text=seg.text.strip(),
                        language=lang,
                    )
                )
        except Exception as e:
            logger.error("Error transcribing chunk %d: %s", i + 1, e)

    # Sort by start time (should be ordered, but ensure)
    all_segments.sort(key=lambda s: s.start)

    if progress_cb:
        langs = {s.language for s in all_segments}
        progress_cb(
            f"✅ Nhận dạng đa ngôn ngữ xong — {len(all_segments)} đoạn, "
            f"ngôn ngữ: {', '.join(sorted(langs))}"
        )

    return all_segments


def segments_to_plain_text(segments: List[TranscriptSegment]) -> str:
    return "\n".join(seg.text for seg in segments)


def segments_to_srt(segments: List[TranscriptSegment]) -> str:
    return "\n".join(seg.to_srt_block(i + 1) for i, seg in enumerate(segments))
