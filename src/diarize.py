"""
diarize.py — Speaker diarization via pyannote.audio 3.1.

Requires:
- A Hugging Face token set in HF_TOKEN env var (or .env).
- User must have accepted model terms at:
  https://huggingface.co/pyannote/speaker-diarization-3.1
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from src.config import HF_TOKEN, DIARIZATION_MODEL

logger = logging.getLogger(__name__)

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        if not HF_TOKEN:
            raise EnvironmentError(
                "HF_TOKEN is not set. Please copy .env.example to .env and "
                "add your Hugging Face token. See README.md for details."
            )
        logger.info("Loading diarization model '%s' …", DIARIZATION_MODEL)
        try:
            import torch
            from pyannote.audio import Pipeline

            _pipeline = Pipeline.from_pretrained(
                DIARIZATION_MODEL,
                use_auth_token=HF_TOKEN,  # Fallback for older versions
            )
            # Trong các phiên bản pyannote.audio mới, use_auth_token bị loại bỏ. Ta dùng thử cách khác.
        except TypeError:
            _pipeline = Pipeline.from_pretrained(
                DIARIZATION_MODEL,
                token=HF_TOKEN,
            )
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            import torch as _torch
            _pipeline = _pipeline.to(_torch.device(device))
            logger.info("Diarization pipeline on device=%s", device)
        except Exception as e:
            raise RuntimeError(f"Failed to load diarization pipeline: {e}") from e
    return _pipeline


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class SpeakerTurn:
    speaker: str   # e.g. "SPEAKER_00"
    start: float   # seconds
    end: float     # seconds


# ── Public API ────────────────────────────────────────────────────────────────

def run(
    audio_path: str | Path,
    num_speakers: Optional[int] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[SpeakerTurn]:
    """
    Run speaker diarization on *audio_path*.

    Parameters
    ----------
    audio_path   : path to the 16 kHz mono WAV.
    num_speakers : if known, pass this to improve accuracy (else auto).
    progress_cb  : optional status string callback.

    Returns
    -------
    List of SpeakerTurn ordered by start time.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    pipeline = _get_pipeline()

    if progress_cb:
        progress_cb("👥 Đang phân tách người nói (pyannote) …")

    kwargs = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers

    # Bypass torchcodec (broken on Windows): load audio via soundfile + torch
    import soundfile as sf_lib
    import torch
    audio_np, sr = sf_lib.read(str(audio_path), dtype="float32")
    # soundfile returns (samples,) for mono or (samples, channels) for stereo
    if audio_np.ndim == 1:
        waveform = torch.from_numpy(audio_np).unsqueeze(0)  # (1, samples)
    else:
        waveform = torch.from_numpy(audio_np.T)  # (channels, samples)
    audio_in_memory = {"waveform": waveform, "sample_rate": sr}

    diarization_result = pipeline(audio_in_memory, **kwargs)

    # pyannote v4 returns DiarizeOutput dataclass; v3 returns Annotation directly
    if hasattr(diarization_result, 'speaker_diarization'):
        annotation = diarization_result.speaker_diarization
    else:
        annotation = diarization_result

    turns: List[SpeakerTurn] = []
    for segment, _, speaker in annotation.itertracks(yield_label=True):
        turns.append(SpeakerTurn(
            speaker=speaker,
            start=segment.start,
            end=segment.end,
        ))

    # Sort by start time (pyannote usually returns them ordered, but be safe)
    turns.sort(key=lambda t: t.start)

    # Normalize speaker labels: SPEAKER_00 → Speaker 1, etc.
    speaker_map: dict[str, str] = {}
    for t in turns:
        if t.speaker not in speaker_map:
            speaker_map[t.speaker] = f"Speaker {len(speaker_map) + 1}"
        t.speaker = speaker_map[t.speaker]

    if progress_cb:
        progress_cb(f"✅ Phân tách xong — {len(speaker_map)} người nói")

    return turns
