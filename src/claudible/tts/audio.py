"""Audio playback utilities."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

log = logging.getLogger(__name__)


def play_audio(audio: np.ndarray, sample_rate: int, lead_in_ms: int = 150) -> None:
    """Play audio array through the default output device.

    *lead_in_ms* prepends silence to let audio sinks (especially Bluetooth)
    wake up before real content starts.  Set to 0 to disable.
    """
    if lead_in_ms > 0:
        lead_in_samples = int(sample_rate * lead_in_ms / 1000)
        silence = np.zeros((lead_in_samples, *audio.shape[1:]), dtype=audio.dtype)
        audio = np.concatenate([silence, audio])
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


def play_file(path: Path) -> None:
    """Play a WAV file through the default output device."""
    data, sr = sf.read(path)
    play_audio(data, sr)
