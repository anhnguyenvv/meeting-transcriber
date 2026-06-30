"""
pipeline.py — End-to-end orchestrator.

Runs the full sequence:
    audio → convert → transcribe → diarize → align → translate → summarize

Saves all artifacts to outputs/<timestamp>__<title>/:
    transcript_original.txt   — speaker-labelled, original language
    transcript_original.srt   — SRT subtitle file
    transcript_vi.txt         — Vietnamese translation
    summary_vi.md             — Vietnamese summary (Markdown)
    metadata.json             — language, duration, speaker count, model versions
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, List, Optional

from src.audio.convert import to_wav_16k_mono, is_already_wav_16k_mono
from src import transcribe, diarize, align, translate, summarize
from src.config import OUTPUTS_DIR, WHISPER_MODEL, OLLAMA_MODEL, DIARIZATION_MODEL
from src.align import AlignedLine
from src.transcribe import TranscriptSegment, segments_to_srt

logger = logging.getLogger(__name__)


# ── Result object ─────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    output_dir: Path
    transcript_original: str    # speaker-labelled, original language
    transcript_vi: str          # Vietnamese translation
    summary_vi: str             # Vietnamese summary (Markdown)
    srt: str                    # SRT subtitles (original language)
    language: str               # detected language code
    speaker_count: int
    duration_s: float
    segments: List[TranscriptSegment]
    aligned_lines: List[AlignedLine]


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    audio_path: str | Path,
    title: str = "meeting",
    num_speakers: Optional[int] = None,
    skip_diarization: bool = False,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> PipelineResult:
    """
    Full pipeline: audio → transcript → diarize → translate → summarize.

    Parameters
    ----------
    audio_path       : path to any audio/video file.
    title            : short label used in output directory name.
    num_speakers     : pass if known (improves diarization accuracy).
    skip_diarization : set True to skip pyannote (useful if HF_TOKEN not set).
    progress_cb      : callback(str) for progress updates.

    Returns
    -------
    PipelineResult with all text artifacts and the output directory path.
    """
    def cb(msg: str) -> None:
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    audio_path = Path(audio_path)
    cb(f"📂 Bắt đầu xử lý: {audio_path.name}")
    t_start = time.time()

    # ── Step 1: Convert to 16 kHz mono WAV ───────────────────────────────────
    cb("🔄 Chuyển đổi định dạng âm thanh …")
    t0 = time.time()
    if is_already_wav_16k_mono(audio_path):
        wav_path = audio_path
    else:
        wav_path = to_wav_16k_mono(audio_path)
    t_convert = time.time() - t0
    cb(f"✅ Đã chuyển đổi: {wav_path.name}")

    # ── Step 2: Transcribe (per-chunk multilingual) ─────────────────────────
    t0 = time.time()
    segments = transcribe.run_multilingual(wav_path, progress_cb=cb)
    detected_langs = sorted({s.language for s in segments}) if segments else ["unknown"]
    detected_lang = detected_langs[0] if len(detected_langs) == 1 else "/".join(detected_langs)
    duration_s = segments[-1].end if segments else 0.0
    t_transcribe = time.time() - t0

    # ── Step 3: Diarize ───────────────────────────────────────────────────────
    t0 = time.time()
    if skip_diarization:
        cb("⏭️ Bỏ qua phân tách người nói")
        turns = []
    else:
        turns = diarize.run(wav_path, num_speakers=num_speakers, progress_cb=cb)
    t_diarize = time.time() - t0

    # ── Step 4: Align ─────────────────────────────────────────────────────────
    cb("🔗 Ghép transcript với thông tin người nói …")
    t0 = time.time()
    aligned_lines = align.merge(segments, turns)
    transcript_original = align.to_text(aligned_lines)
    srt_content = segments_to_srt(segments)
    speaker_count = len({line.speaker for line in aligned_lines})
    t_align = time.time() - t0
    cb(f"✅ Ghép xong — {len(aligned_lines)} khối, {speaker_count} người nói")

    # ── Step 5: Translate ─────────────────────────────────────────────────────
    t0 = time.time()
    transcript_vi = translate.to_vi(transcript_original, progress_cb=cb)
    t_translate = time.time() - t0

    # ── Step 6: Summarize ─────────────────────────────────────────────────────
    t0 = time.time()
    llm_input = align.to_plain_text_for_llm(aligned_lines)
    summary_vi = summarize.to_vi(llm_input, progress_cb=cb)
    t_summarize = time.time() - t0

    t_total = time.time() - t_start
    rtf = t_total / duration_s if duration_s > 0 else 0.0

    # ── Step 7: Save artifacts ────────────────────────────────────────────────
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:40]
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUTS_DIR / f"{ts}__{safe_title}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "transcript_original.txt").write_text(transcript_original, encoding="utf-8")
    (out_dir / "transcript_original.srt").write_text(srt_content, encoding="utf-8")
    (out_dir / "transcript_vi.txt").write_text(transcript_vi, encoding="utf-8")
    (out_dir / "summary_vi.md").write_text(summary_vi, encoding="utf-8")
    (out_dir / "metadata.json").write_text(
        json.dumps({
            "title": title,
            "language": detected_lang,
            "duration_s": round(duration_s, 2),
            "speaker_count": speaker_count,
            "segment_count": len(segments),
            "whisper_model": WHISPER_MODEL,
            "diarization_model": DIARIZATION_MODEL if not skip_diarization else "skipped",
            "ollama_model": OLLAMA_MODEL,
            "created_at": ts,
            "metrics": {
                "conversion_time_s": round(t_convert, 2),
                "transcription_time_s": round(t_transcribe, 2),
                "diarization_time_s": round(t_diarize, 2),
                "alignment_time_s": round(t_align, 2),
                "translation_time_s": round(t_translate, 2),
                "summarization_time_s": round(t_summarize, 2),
                "total_time_s": round(t_total, 2),
                "rtf": round(rtf, 4)
            }
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cb(f"💾 Đã lưu kết quả vào: {out_dir}")

    return PipelineResult(
        output_dir=out_dir,
        transcript_original=transcript_original,
        transcript_vi=transcript_vi,
        summary_vi=summary_vi,
        srt=srt_content,
        language=detected_lang,
        speaker_count=speaker_count,
        duration_s=duration_s,
        segments=segments,
        aligned_lines=aligned_lines,
    )
