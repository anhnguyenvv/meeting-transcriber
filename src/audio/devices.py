"""
devices.py — List audio input devices available on the current machine.
Cross-platform (macOS / Windows) via sounddevice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import sounddevice as sd

from src.config import LOOPBACK_DEVICE_HINT


@dataclass
class AudioDevice:
    index: int
    name: str
    max_input_channels: int
    default_sample_rate: float

    def __str__(self) -> str:
        return f"[{self.index}] {self.name} ({int(self.default_sample_rate)} Hz, {self.max_input_channels}ch)"


def list_input_devices() -> List[AudioDevice]:
    """Return all input-capable audio devices."""
    devices = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            devices.append(
                AudioDevice(
                    index=i,
                    name=d["name"],
                    max_input_channels=d["max_input_channels"],
                    default_sample_rate=d["default_samplerate"],
                )
            )
    return devices


def device_names() -> List[str]:
    """Return device names for Gradio Dropdown."""
    return [str(d) for d in list_input_devices()]


def find_loopback_device() -> AudioDevice | None:
    """Try to auto-select the system-audio loopback device."""
    for d in list_input_devices():
        if LOOPBACK_DEVICE_HINT.lower() in d.name.lower():
            return d
    return None


def device_by_label(label: str) -> AudioDevice | None:
    """Look up a device from the string produced by device_names()."""
    # 1. Exact match (fastest, works 99% of the time)
    for d in list_input_devices():
        if str(d) == label:
            return d
    
    # 2. Fallback match by name
    # Occurs when user unplugs/plugs a device while the app is running,
    # causing device indexes to shift. The frontend might send an outdated label string 
    # e.g., "[2] CABLE Output..." but it's now index [3].
    for d in list_input_devices():
        # Match if the device name is present in the label string
        if d.name in label:
            return d
            
    return None
