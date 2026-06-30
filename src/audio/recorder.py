"""
recorder.py — Live audio capture (mic or loopback device).

Usage:
    rec = AudioRecorder(device_index=3)
    rec.start()
    ...
    path = rec.stop()   # returns Path to saved .wav
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

from src.config import SAMPLE_RATE, OUTPUTS_DIR


class AudioRecorder:
    """Thread-safe audio recorder. Records until stop() is called."""

    def __init__(self, device_index: Optional[int] = None, sample_rate: int = SAMPLE_RATE):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self._frames: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self._recording = False

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin recording. Non-blocking."""
        if self._recording:
            return
        self._frames.clear()
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device_index,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> Path:
        """Stop recording and save to WAV. Returns file path."""
        if not self._recording:
            raise RuntimeError("Recorder is not running.")
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        audio = np.concatenate(self._frames, axis=0) if self._frames else np.zeros((0, 1), dtype="float32")
        out_path = OUTPUTS_DIR / f"rec_{int(time.time())}.wav"
        sf.write(str(out_path), audio, self.sample_rate)
        return out_path

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ── Internal ──────────────────────────────────────────────────────────────

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        with self._lock:
            self._frames.append(indata.copy())
