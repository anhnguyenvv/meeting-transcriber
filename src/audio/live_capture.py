"""
live_capture.py — Dual-source live audio capture (mic + system loopback).

Inspired by Meetily's Audio Engine design:
  - Captures microphone and system audio simultaneously
  - Mixes both streams into a single rolling buffer
  - Provides fixed-size chunks with configurable overlap for streaming Whisper
  - Applies gain normalization and clipping prevention

Usage:
    cap = LiveCapture(mic_device=0, loopback_device=3)
    cap.start()
    while cap.is_running:
        chunk = cap.get_chunk()  # blocks until chunk is ready
        if chunk is not None:
            process(chunk)
    cap.stop()
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd

from src.config import (
    SAMPLE_RATE,
    LIVE_CHUNK_DURATION_S,
    LIVE_OVERLAP_S,
    LIVE_SILENCE_THRESHOLD,
)

logger = logging.getLogger(__name__)


@dataclass
class AudioChunk:
    """A chunk of audio ready for transcription."""
    data: np.ndarray       # float32 mono, shape (samples,)
    timestamp: float       # wall-clock time when chunk was finalized
    offset_s: float        # offset from session start in seconds
    duration_s: float      # chunk duration in seconds
    is_silent: bool        # True if chunk is mostly silence


class LiveCapture:
    """
    Dual-source audio capture with rolling buffer and chunk delivery.

    Can operate with:
      - mic only
      - loopback only
      - mic + loopback (mixed)
    """

    def __init__(
        self,
        mic_device: Optional[int] = None,
        loopback_device: Optional[int] = None,
        sample_rate: int = SAMPLE_RATE,
        chunk_duration_s: float = LIVE_CHUNK_DURATION_S,
        overlap_s: float = LIVE_OVERLAP_S,
        silence_threshold: float = LIVE_SILENCE_THRESHOLD,
    ):
        if mic_device is None and loopback_device is None:
            raise ValueError("At least one audio source (mic or loopback) is required")

        self.mic_device = mic_device
        self.loopback_device = loopback_device
        self.sample_rate = sample_rate
        self.chunk_duration_s = chunk_duration_s
        self.overlap_s = overlap_s
        self.silence_threshold = silence_threshold

        # Computed
        self._chunk_samples = int(chunk_duration_s * sample_rate)
        self._overlap_samples = int(overlap_s * sample_rate)
        self._step_samples = self._chunk_samples - self._overlap_samples

        # State
        self._mic_stream = None
        self._loopback_stream = None
        self._mic_pa = None
        self._lb_pa = None
        self._running = False
        self._start_time = 0.0
        self._total_samples_delivered = 0

        # Separate buffers for mic and loopback to mix them correctly
        self._mic_buffer = np.zeros(0, dtype="float32")
        self._lb_buffer = np.zeros(0, dtype="float32")
        self._buffer_lock = threading.Lock()

        # Output queue for chunks
        self._chunk_queue: deque[AudioChunk] = deque(maxlen=100)
        self._chunk_event = threading.Event()

        # Worker thread to produce chunks from buffer
        self._worker: Optional[threading.Thread] = None

        import scipy.signal
        import math
        def safe_resample(x, orig_sr, target_sr):
            if orig_sr == target_sr: return x
            d = math.gcd(int(orig_sr), int(target_sr))
            out = scipy.signal.resample_poly(x, int(target_sr) // d, int(orig_sr) // d)
            target_len = int(len(x) * target_sr / orig_sr)
            if len(out) > target_len:
                out = out[:target_len]
            elif len(out) < target_len:
                out = np.pad(out, (0, target_len - len(out)))
            return out
        self._resample = safe_resample

        self._mic_native_rate = 16000
        self._lb_native_rate = 16000

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def _start_stream(self, device_idx: int, callback, is_mic: bool):
        """Starts a stream using pyaudiowpatch with native WASAPI support."""
        import pyaudiowpatch as pyaudio
        p = pyaudio.PyAudio()
        info = p.get_device_info_by_index(device_idx)
        native_rate = int(info['defaultSampleRate'])
        channels = info['maxInputChannels']

        if is_mic:
            self._mic_native_rate = native_rate
        else:
            self._lb_native_rate = native_rate
            
        def pa_callback(in_data, frame_count, time_info, status):
            data_np = np.frombuffer(in_data, dtype=np.float32)
            # Mix down to mono if needed
            if channels > 1:
                data_np = data_np.reshape(-1, channels).mean(axis=1)
                
            callback(data_np, frame_count, time_info, status)
            return (None, pyaudio.paContinue)

        stream = p.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=native_rate,
            input=True,
            input_device_index=device_idx,
            stream_callback=pa_callback,
            frames_per_buffer=int(native_rate * 0.1)
        )
        stream.start_stream()
        return p, stream

    def start(self) -> None:
        """Start capturing audio from configured sources."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()
        self._total_samples_delivered = 0
        self._mic_buffer = np.zeros(0, dtype="float32")
        self._lb_buffer = np.zeros(0, dtype="float32")
        self._chunk_queue.clear()
        self._full_audio_buffer = []

        # Start input streams
        if self.mic_device is not None:
            self._mic_pa, self._mic_stream = self._start_stream(self.mic_device, self._mic_callback, is_mic=True)
            logger.info("Mic stream started (device=%s, rate=%s)", self.mic_device, self._mic_native_rate)

        if self.loopback_device is not None:
            self._lb_pa, self._loopback_stream = self._start_stream(self.loopback_device, self._loopback_callback, is_mic=False)
            logger.info("Loopback stream started (device=%s, rate=%s)", self.loopback_device, self._lb_native_rate)

        # Start chunk-producer worker
        self._worker = threading.Thread(target=self._chunk_worker, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Stop all capture streams and worker."""
        self._running = False

        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()
            self._mic_stream = None
        if self._mic_pa:
            self._mic_pa.terminate()
            self._mic_pa = None

        if self._loopback_stream:
            self._loopback_stream.stop_stream()
            self._loopback_stream.close()
            self._loopback_stream = None
        if self._lb_pa:
            self._lb_pa.terminate()
            self._lb_pa = None

        self._chunk_event.set()  # wake worker to exit

        if self._worker:
            self._worker.join(timeout=2)
            self._worker = None

        logger.info("LiveCapture stopped")

    def get_chunk(self, timeout: float = 2.0) -> Optional[AudioChunk]:
        """
        Get the next audio chunk. Blocks up to *timeout* seconds.
        Returns None if no chunk is available or capture has stopped.
        """
        if self._chunk_queue:
            return self._chunk_queue.popleft()

        self._chunk_event.wait(timeout=timeout)
        self._chunk_event.clear()

        if self._chunk_queue:
            return self._chunk_queue.popleft()
        return None

    def get_elapsed_s(self) -> float:
        """Seconds since capture started."""
        if not self._running:
            return 0.0
        return time.time() - self._start_time

    def get_full_audio(self) -> np.ndarray:
        """Return the complete continuous audio recorded during this session."""
        if not hasattr(self, '_full_audio_buffer') or not self._full_audio_buffer:
            return np.zeros(0, dtype="float32")
        return np.concatenate(self._full_audio_buffer, axis=0)

    # ── Callbacks ─────────────────────────────────────────────────────────────
    # KEEP CALLBACKS AS FAST AS POSSIBLE (ZERO MATH) TO PREVENT CRACKLING
    def _mic_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status: logger.debug("Mic status: %s", status)
        mono = indata[:, 0] if indata.ndim > 1 else indata.ravel()
        with self._buffer_lock:
            self._mic_buffer = np.concatenate([self._mic_buffer, mono])

    def _loopback_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status: logger.debug("Loopback status: %s", status)
        mono = indata[:, 0] if indata.ndim > 1 else indata.ravel()
        with self._buffer_lock:
            self._lb_buffer = np.concatenate([self._lb_buffer, mono])

    # ── Worker ────────────────────────────────────────────────────────────────

    def _chunk_worker(self) -> None:
        """Background thread: slice chunks from buffer when enough data is ready."""
        while self._running:
            chunk = self._try_extract_chunk()
            if chunk is not None:
                self._chunk_queue.append(chunk)
                self._chunk_event.set()
            else:
                time.sleep(0.1)  # poll interval
                
        # Drain the final remaining buffer when stopping
        chunk = self._try_extract_chunk(force=True)
        if chunk is not None:
            self._chunk_queue.append(chunk)
            self._chunk_event.set()

    def _try_extract_chunk(self, force: bool = False) -> Optional[AudioChunk]:
        """Try to extract a chunk from the buffer. Returns None if not enough data unless force=True."""
        with self._buffer_lock:
            # Calculate required samples at native rates
            mic_req = int(self.chunk_duration_s * self._mic_native_rate)
            lb_req = int(self.chunk_duration_s * self._lb_native_rate)
            
            mic_step = int((self.chunk_duration_s - self.overlap_s) * self._mic_native_rate)
            lb_step = int((self.chunk_duration_s - self.overlap_s) * self._lb_native_rate)

            # Check if we have enough data in either active buffer
            mic_ok = self.mic_device is None or len(self._mic_buffer) >= mic_req
            lb_ok = self.loopback_device is None or len(self._lb_buffer) >= lb_req
            
            if not force and not (mic_ok and lb_ok):
                return None
                
            # If force=True, we process whatever is left
            if force:
                if self.mic_device is not None and len(self._mic_buffer) == 0:
                    mic_ok = False
                if self.loopback_device is not None and len(self._lb_buffer) == 0:
                    lb_ok = False
                if not mic_ok and not lb_ok:
                    return None
                mic_req = len(self._mic_buffer) if self.mic_device is not None else 0
                lb_req = len(self._lb_buffer) if self.loopback_device is not None else 0
                mic_step = mic_req
                lb_step = lb_req
                
            # Extract native chunks
            mic_raw = None
            lb_raw = None
            
            if self.mic_device is not None:
                mic_raw = self._mic_buffer[:mic_req].copy()
                self._mic_buffer = self._mic_buffer[mic_step:]
                
            if self.loopback_device is not None:
                lb_raw = self._lb_buffer[:lb_req].copy()
                self._lb_buffer = self._lb_buffer[lb_step:]
                
        mic_processed = None
        lb_processed = None
        
        if mic_raw is not None:
            if self._mic_native_rate != self.sample_rate:
                mic_raw = self._resample(mic_raw, self._mic_native_rate, self.sample_rate)
            # Truncate or pad to exactly chunk_samples
            if len(mic_raw) > self._chunk_samples: mic_raw = mic_raw[:self._chunk_samples]
            elif len(mic_raw) < self._chunk_samples: mic_raw = np.pad(mic_raw, (0, self._chunk_samples - len(mic_raw)))
            mic_processed = mic_raw
            
        if lb_raw is not None:
            if self._lb_native_rate != self.sample_rate:
                lb_raw = self._resample(lb_raw, self._lb_native_rate, self.sample_rate)
            if len(lb_raw) > self._chunk_samples: lb_raw = lb_raw[:self._chunk_samples]
            elif len(lb_raw) < self._chunk_samples: lb_raw = np.pad(lb_raw, (0, self._chunk_samples - len(lb_raw)))
            lb_processed = lb_raw

        # Smart Mixing (Ducking)
        if mic_processed is not None and lb_processed is not None:
            # 1. Tính cường độ (envelope) của loa hệ thống
            sys_env = np.abs(lb_processed)
            # 2. Nếu loa đang phát tiếng ( > 0.05 ), mục tiêu gain của mic = 0.3, ngược lại 1.0
            target_gain = np.where(sys_env > 0.05, 0.3, 1.0)
            # 3. Làm mượt (Smooth) gain bằng sliding window 100ms để tránh giật cục (clicks)
            window_size = int(self.sample_rate * 0.1)
            if window_size > 0:
                window = np.ones(window_size) / window_size
                smoothed_gain = np.convolve(target_gain, window, mode='same')
            else:
                smoothed_gain = target_gain
            # 4. Trộn hai luồng
            mixed = (mic_processed * smoothed_gain) + lb_processed
        elif mic_processed is not None:
            mixed = mic_processed
        elif lb_processed is not None:
            mixed = lb_processed
        else:
            mixed = np.zeros(self._chunk_samples, dtype="float32")

        # Normalize — prevent clipping, apply soft gain
        chunk_data = self._normalize(mixed)

        # Check silence
        rms = np.sqrt(np.mean(chunk_data ** 2))
        is_silent = rms < self.silence_threshold

        offset = self._total_samples_delivered / self.sample_rate
        self._total_samples_delivered += self._step_samples

        # Lưu lại phần không trùng lặp (non-overlapping) để nối file sau
        if hasattr(self, '_full_audio_buffer'):
            self._full_audio_buffer.append(chunk_data[:self._step_samples].copy())

        return AudioChunk(
            data=chunk_data,
            timestamp=time.time(),
            offset_s=offset,
            duration_s=self.chunk_duration_s,
            is_silent=is_silent,
        )

    @staticmethod
    def _normalize(audio: np.ndarray) -> np.ndarray:
        """Soft normalization with clipping prevention."""
        peak = np.abs(audio).max()
        if peak > 0.95:
            # Reduce gain to prevent clipping
            audio = audio * (0.9 / peak)
        return audio
