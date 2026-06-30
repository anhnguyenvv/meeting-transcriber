"""
align.py — Merge Whisper transcript segments with pyannote speaker turns.

Algorithm:
    For each Whisper segment, find the speaker whose turn has the most
    overlap with the segment's [start, end] window.  If there is no
    overlapping turn, assign the speaker of the nearest turn (by midpoint).

    Consecutive lines from the same speaker are then collapsed into blocks
    to produce a readable transcript.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from src.transcribe import TranscriptSegment
from src.diarize import SpeakerTurn


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class AlignedLine:
    speaker: str
    start: float
    end: float
    text: str
    language: str

    def timestamp(self) -> str:
        def fmt(s: float) -> str:
            m, sec = divmod(int(s), 60)
            return f"{m:02}:{sec:02}"
        return f"{fmt(self.start)} → {fmt(self.end)}"

    def __str__(self) -> str:
        return f"{self.speaker} [{self.timestamp()}]: {self.text}"


# ── Public API ────────────────────────────────────────────────────────────────

def merge(
    segments: List[TranscriptSegment],
    turns: List[SpeakerTurn],
) -> List[AlignedLine]:
    """
    Assign a speaker to every TranscriptSegment and collapse runs.

    Parameters
    ----------
    segments : list from transcribe.run()
    turns    : list from diarize.run()

    Returns
    -------
    List of AlignedLine with speaker labels and collapsed blocks.
    """
    if not segments:
        return []

    # If diarization is empty (e.g. skipped), assign a single speaker
    if not turns:
        return [
            AlignedLine(
                speaker="Speaker 1",
                start=seg.start,
                end=seg.end,
                text=seg.text,
                language=seg.language,
            )
            for seg in segments
        ]

    labeled: List[AlignedLine] = []
    for seg in segments:
        speaker = _best_speaker(seg.start, seg.end, turns)
        labeled.append(AlignedLine(
            speaker=speaker,
            start=seg.start,
            end=seg.end,
            text=seg.text,
            language=seg.language,
        ))

    return _collapse(labeled)


def to_text(lines: List[AlignedLine]) -> str:
    """Human-readable transcript string."""
    return "\n".join(str(line) for line in lines)


def to_plain_text_for_llm(lines: List[AlignedLine]) -> str:
    """Slightly more compact version used as LLM input."""
    return "\n".join(f"{line.speaker}: {line.text}" for line in lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _best_speaker(seg_start: float, seg_end: float, turns: List[SpeakerTurn]) -> str:
    # Try maximum overlap first
    best_turn: Optional[SpeakerTurn] = None
    best_overlap = 0.0
    for turn in turns:
        ov = _overlap(seg_start, seg_end, turn.start, turn.end)
        if ov > best_overlap:
            best_overlap = ov
            best_turn = turn

    if best_turn is not None and best_overlap > 0:
        return best_turn.speaker

    # Fallback: nearest turn by midpoint distance
    seg_mid = (seg_start + seg_end) / 2
    best_turn = min(turns, key=lambda t: abs((t.start + t.end) / 2 - seg_mid))
    return best_turn.speaker


def _collapse(lines: List[AlignedLine]) -> List[AlignedLine]:
    """Merge consecutive same-speaker lines into blocks."""
    if not lines:
        return []
    collapsed: List[AlignedLine] = [lines[0]]
    for line in lines[1:]:
        prev = collapsed[-1]
        if line.speaker == prev.speaker:
            prev.text = prev.text.rstrip() + " " + line.text.lstrip()
            prev.end = line.end
        else:
            collapsed.append(line)
    return collapsed
