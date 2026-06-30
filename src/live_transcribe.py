"""
live_transcribe.py — Real-time streaming transcription engine.

Consumes audio chunks from LiveCapture and produces live transcript
updates. Uses per-chunk language detection for multilingual meetings.

Architecture (inspired by Meetily):
    LiveCapture → AudioChunk → LiveTranscriber → TranscriptUpdate → UI

Features:
    - Per-chunk language detection (JA / EN / VI code-switching)
    - Overlap-aware deduplication (avoids repeating words at chunk boundaries)
    - Thread-safe transcript accumulation
    - Session save on stop (full transcript + translation + summary)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
import soundfile as sf

from src.config import SAMPLE_RATE, OUTPUTS_DIR
from src.transcribe import TranscriptSegment, _get_model, _detect_language

logger = logging.getLogger(__name__)


@dataclass
class TranscriptUpdate:
    """A single update from the live transcriber."""
    text: str               # new text from this chunk
    language: str           # detected language for this chunk
    timestamp_s: float      # offset from session start
    is_partial: bool        # True if this may be revised by next chunk


@dataclass
class LiveSession:
    """Accumulated state for a live transcription session."""
    title: str = "live_meeting"
    start_time: float = 0.0
    updates: List[TranscriptUpdate] = field(default_factory=list)
    segments: List[TranscriptSegment] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_update(self, update: TranscriptUpdate) -> None:
        with self._lock:
            self.updates.append(update)

    def add_segments(self, segs: List[TranscriptSegment]) -> None:
        with self._lock:
            self.segments.extend(segs)

    def get_full_text(self) -> str:
        with self._lock:
            return "\n".join(u.text for u in self.updates if u.text.strip())

    def get_languages(self) -> set[str]:
        with self._lock:
            return {u.language for u in self.updates}

    def get_duration_s(self) -> float:
        if not self.start_time:
            return 0.0
        return time.time() - self.start_time


class LiveTranscriber:
    """
    Streaming transcription engine.

    Consumes AudioChunks, runs Whisper inference with per-chunk language
    detection, and accumulates results into a LiveSession.
    """

    def __init__(
        self,
        title: str = "live_meeting",
        on_update: Optional[Callable[[TranscriptUpdate], None]] = None,
        force_language: Optional[str] = None,
    ):
        """
        Parameters
        ----------
        title          : session title (used for output directory).
        on_update      : callback fired for each new transcript chunk.
        force_language : if set (e.g. "vi", "en"), bypasses auto-detect and forces this language.
        """
        self.title = title
        self.on_update = on_update
        self.force_language = force_language

        self.session = LiveSession(title=title)
        self._running = False
        self._previous_text = ""  # for deduplication

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Initialize a new session."""
        self._running = True
        self.session = LiveSession(title=self.title, start_time=time.time())
        self._previous_text = ""
        logger.info("LiveTranscriber started — session=%s, force_lang=%s", self.title, self.force_language)

    def stop(self) -> Path:
        """
        Stop the session and save all artifacts.
        Returns the output directory path.
        """
        self._running = False
        out_dir = self._save_session()
        logger.info("LiveTranscriber stopped — saved to %s", out_dir)
        return out_dir

    def process_chunk(self, audio_data: np.ndarray, offset_s: float) -> Optional[TranscriptUpdate]:
        """
        Transcribe a single audio chunk and return the update.

        Parameters
        ----------
        audio_data : float32 mono audio array at SAMPLE_RATE
        offset_s   : time offset from session start

        Returns
        -------
        TranscriptUpdate or None if chunk was silent/empty.
        """
        if not self._running:
            return None

        model = _get_model()

        # Detect language for this chunk or use forced language
        if self.force_language:
            lang = self.force_language
            prob = 1.0
        else:
            lang, prob = _detect_language(model, audio_data)
        
        # Smooth language switching (avoid hallucinating rare languages on noise)
        if prob < 0.6 and hasattr(self, "_last_lang"):
            lang = self._last_lang
        else:
            self._last_lang = lang

        # Transcribe trực tiếp từ bộ nhớ (numpy array) và kích hoạt VAD để lọc nhiễu
        try:
            t0 = time.time()
            segments_iter, _ = model.transcribe(
                audio_data,
                language=lang,
                initial_prompt=self._previous_text[-200:] if self._previous_text else None,
                task="transcribe",
                vad_filter=True,  # Kích hoạt Silero VAD để lọc tiếng thở/tiếng ồn nền
                vad_parameters={
                    "min_silence_duration_ms": 500,  # Thời gian im lặng tối thiểu để phân tách phân đoạn
                    "speech_pad_ms": 100             # Padding thêm vào trước/sau đoạn giọng nói để tránh mất từ
                },
                beam_size=1,       # GIẢM XUỐNG 1 ĐỂ TĂNG TỐC ĐỘ GẤP 3 LẦN (Live mode ưu tiên tốc độ)
                condition_on_previous_text=False,
                word_timestamps=False,
            )

            chunk_segments: List[TranscriptSegment] = []
            chunk_texts: List[str] = []

            for seg in segments_iter:
                text = seg.text.strip()
                if text:
                    ts = TranscriptSegment(
                        start=seg.start + offset_s,
                        end=seg.end + offset_s,
                        text=text,
                        language=lang
                    )
                    chunk_segments.append(ts)
                    chunk_texts.append(text)
                    
            t1 = time.time()
            process_time = t1 - t0
            logger.info("⚡ Chunk at %.1fs processed in %.2fs (Lang: %s, Score: %.2f)", offset_s, process_time, lang, prob)

        if not chunk_texts:
            return None

        # Deduplicate against previous chunk (overlap region)
        new_text = " ".join(chunk_texts)
        deduped = self._deduplicate(new_text)

        if not deduped.strip():
            return None

        # Build update
        update = TranscriptUpdate(
            text=deduped,
            language=lang,
            timestamp_s=offset_s,
            is_partial=False,
        )

        self.session.add_update(update)
        self.session.add_segments(chunk_segments)

        if self.on_update:
            try:
                self.on_update(update)
            except Exception:
                logger.exception("on_update callback error")

        self._previous_text = new_text
        return update

    def _deduplicate(self, new_text: str) -> str:
        """
        Remove overlapping text between previous and current chunk.

        Uses a suffix-prefix matching algorithm: finds the longest suffix
        of the previous text that matches a prefix of the new text.
        """
        if not self._previous_text:
            return new_text

        prev_words = self._previous_text.split()
        new_words = new_text.split()

        if not prev_words or not new_words:
            return new_text

        # Find longest overlap (check last N words of prev against first N of new)
        max_check = min(len(prev_words), len(new_words), 15)  # cap at 15 words

        best_overlap = 0
        for length in range(1, max_check + 1):
            prev_suffix = prev_words[-length:]
            new_prefix = new_words[:length]
            if prev_suffix == new_prefix:
                best_overlap = length

        if best_overlap > 0:
            deduped_words = new_words[best_overlap:]
            return " ".join(deduped_words)

        return new_text

    def _save_session(self) -> Path:
        """Save all session artifacts to disk."""
        safe_title = "".join(
            c if c.isalnum() or c in "-_ " else "_" for c in self.title
        )[:40]
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = OUTPUTS_DIR / f"{ts}__live__{safe_title}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Full transcript
        full_text = self.session.get_full_text()
        (out_dir / "transcript_live.txt").write_text(full_text, encoding="utf-8")

        # Metadata
        langs = sorted(self.session.get_languages())
        duration = self.session.get_duration_s()
        metadata = {
            "title": self.title,
            "mode": "live",
            "languages": langs,
            "duration_s": round(duration, 2),
            "update_count": len(self.session.updates),
            "segment_count": len(self.session.segments),
            "created_at": ts,
        }
        (out_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # SRT from segments
        from src.transcribe import segments_to_srt
        srt = segments_to_srt(self.session.segments)
        (out_dir / "transcript_live.srt").write_text(srt, encoding="utf-8")

        logger.info(
            "Session saved: %d updates, %d segments, %.1f min, langs=%s",
            len(self.session.updates),
            len(self.session.segments),
            duration / 60,
            langs,
        )

        return out_dir
