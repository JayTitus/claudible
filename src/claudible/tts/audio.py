"""Audio playback utilities."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

log = logging.getLogger(__name__)


def play_audio(audio: np.ndarray, sample_rate: int) -> None:
    """Play audio array through the default output device."""
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


def play_file(path: Path) -> None:
    """Play a WAV file through the default output device."""
    data, sr = sf.read(path)
    play_audio(data, sr)
