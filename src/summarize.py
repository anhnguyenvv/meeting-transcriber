"""
summarize.py — Generate a structured Vietnamese meeting summary via Ollama.

Uses the original-language transcript (speaker-labelled) as input.
Qwen2.5 7B has a 128k-token context window, so even long meetings fit in
a single request.  If the transcript is very long (>40k chars), it is
truncated with a note — a future version can use map-reduce chunking.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from src.ollama_client import chat

logger = logging.getLogger(__name__)

_MAX_TRANSCRIPT_CHARS = 40_000   # safety limit before single-request

_SYSTEM_PROMPT = """\
Bạn là một trợ lý họp thông minh, thành thạo tiếng Việt, tiếng Anh và tiếng Nhật.

Nhiệm vụ: Dựa vào bản ghi nội dung cuộc họp dưới đây (có thể bằng tiếng Anh, tiếng Nhật hoặc tiếng Việt), \
hãy viết một bản TÓM TẮT BẰNG TIẾNG VIỆT theo đúng cấu trúc sau:

---
# Tóm tắt cuộc họp

## 1. Bối cảnh
(Mô tả ngắn gọn: cuộc họp về chủ đề gì, ai tham dự, khi nào)

## 2. Các điểm chính
- (Bullet point mỗi ý chính được thảo luận)

## 3. Quyết định đã đưa ra
- (Liệt kê các quyết định cụ thể)

## 4. Hành động cần thực hiện
| Người phụ trách | Việc cần làm | Hạn chót |
|---|---|---|
| (Tên/Speaker) | (Mô tả việc) | (Ngày nếu đề cập, nếu không ghi "Chưa xác định") |

## 5. Câu hỏi còn mở / Vấn đề chưa giải quyết
- (Liệt kê nếu có, nếu không ghi "Không có")
---

Chỉ viết phần tóm tắt theo đúng cấu trúc trên. Không thêm lời mở đầu hay kết thúc.
"""


def to_vi(
    labelled_transcript: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Summarize the meeting transcript in Vietnamese.

    Parameters
    ----------
    labelled_transcript : speaker-labelled original transcript string.
    progress_cb         : optional status callback.

    Returns
    -------
    Structured Vietnamese summary as Markdown.
    """
    if not labelled_transcript.strip():
        return "*(Không có nội dung để tóm tắt)*"

    if progress_cb:
        progress_cb("📝 Đang tạo tóm tắt tiếng Việt …")

    # Truncate if too long (simple safeguard)
    transcript_input = labelled_transcript
    if len(labelled_transcript) > _MAX_TRANSCRIPT_CHARS:
        transcript_input = (
            labelled_transcript[:_MAX_TRANSCRIPT_CHARS]
            + "\n\n[... nội dung bị cắt bớt do quá dài ...]"
        )
        logger.warning("Transcript truncated to %d chars for summarization.", _MAX_TRANSCRIPT_CHARS)

    summary = chat(_SYSTEM_PROMPT, transcript_input)

    if progress_cb:
        progress_cb("✅ Tóm tắt xong!")

    return summary.strip()
