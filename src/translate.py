"""
translate.py — Translate the labelled transcript to Vietnamese via Ollama.

The transcript is split into chunks to keep each request fast and well
within the model's context window.  Chunks are stitched back preserving
speaker labels and timestamps.
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

from src.config import TRANSLATION_CHUNK_CHARS, TRANSLATION_OVERLAP_CHARS
from src.ollama_client import chat

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Bạn là một biên dịch viên chuyên nghiệp, thành thạo tiếng Việt, tiếng Anh và tiếng Nhật.

Nhiệm vụ: Dịch chính xác đoạn hội thoại dưới đây sang tiếng Việt tự nhiên, rõ ràng.

Quy tắc bắt buộc:
- Giữ nguyên nhãn người nói (ví dụ: "Speaker 1", "Speaker 2", ...) và mốc thời gian (ví dụ: [02:15 → 02:45]).
- Chỉ dịch phần nội dung, KHÔNG thêm bình luận, giải thích hay ghi chú.
- Nếu đoạn đã là tiếng Việt, giữ nguyên (sửa lỗi chính tả nếu có).
- Dịch sát nghĩa, tự nhiên — không dịch máy móc.
"""


def to_vi(
    labelled_transcript: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Translate *labelled_transcript* to Vietnamese.

    Parameters
    ----------
    labelled_transcript : output of align.to_text() — speaker-labelled text.
    progress_cb         : optional status callback.

    Returns
    -------
    Vietnamese translation as a single string.
    """
    if not labelled_transcript.strip():
        return ""

    chunks = _split_into_chunks(
        labelled_transcript,
        chunk_size=TRANSLATION_CHUNK_CHARS,
        overlap=TRANSLATION_OVERLAP_CHARS,
    )

    if progress_cb:
        progress_cb(f"🌐 Đang dịch sang tiếng Việt ({len(chunks)} đoạn) …")

    translated_parts: List[str] = []
    for i, chunk in enumerate(chunks, 1):
        if progress_cb:
            progress_cb(f"🌐 Dịch đoạn {i}/{len(chunks)} …")
        translated = chat(_SYSTEM_PROMPT, chunk)
        translated_parts.append(translated.strip())

    result = "\n\n".join(translated_parts)

    if progress_cb:
        progress_cb("✅ Dịch xong!")

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_into_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Split text into chunks of ≤ chunk_size chars with a small overlap.
    Split only at newlines to avoid cutting speaker labels mid-line.
    """
    lines = text.splitlines(keepends=True)
    chunks: List[str] = []
    current = ""

    for line in lines:
        if len(current) + len(line) > chunk_size and current:
            chunks.append(current)
            # Start new chunk with overlap: grab last N chars of previous chunk
            overlap_text = current[-overlap:] if overlap else ""
            current = overlap_text + line
        else:
            current += line

    if current.strip():
        chunks.append(current)

    return chunks
