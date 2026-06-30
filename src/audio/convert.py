"""
convert.py — Convert any audio/video file to 16 kHz mono WAV for Whisper.
Uses imageio-ffmpeg so no separate ffmpeg install is needed.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import imageio_ffmpeg


def to_wav_16k_mono(src: str | Path, dst: str | Path | None = None) -> Path:
    """
    Convert *src* to a 16 kHz mono PCM WAV file.

    Parameters
    ----------
    src : path to the input file (any format ffmpeg understands)
    dst : optional output path; if None, a sibling file is created next to src.

    Returns
    -------
    Path to the output .wav file.
    """
    src = Path(src)
    if dst is None:
        dst = src.parent / f"{src.stem}_{int(time.time())}_16k.wav"
    dst = Path(dst)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",                  # overwrite without prompting
        "-i", str(src),
        "-ar", "16000",        # 16 kHz sample rate
        "-ac", "1",            # mono
        "-sample_fmt", "s16",  # 16-bit PCM
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg conversion failed:\n{result.stderr}"
        )
    return dst


def is_already_wav_16k_mono(path: str | Path) -> bool:
    """Quick check using ffprobe (bundled with imageio-ffmpeg)."""
    path = Path(path)
    if path.suffix.lower() != ".wav":
        return False
    # If it's a .wav, try probing; on failure assume False
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe = ffmpeg_exe.replace("ffmpeg", "ffprobe")
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_streams", str(path)],
            capture_output=True, text=True,
        )
        import json
        info = json.loads(result.stdout)
        streams = info.get("streams", [])
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if audio is None:
            return False
        return (
            int(audio.get("sample_rate", 0)) == 16000
            and int(audio.get("channels", 0)) == 1
        )
    except Exception:
        return False
