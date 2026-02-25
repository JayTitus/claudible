"""Voice management — discovering, adding, and selecting voice profiles."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from claudible.paths import VOICES_DIR, ensure_dirs


@dataclass
class Voice:
    name: str
    path: Path

    @property
    def wav_file(self) -> Path:
        """Return the first .wav file in the voice directory."""
        wavs = list(self.path.glob("*.wav"))
        if not wavs:
            raise FileNotFoundError(f"No .wav files found for voice '{self.name}'")
        return wavs[0]

    @property
    def exists(self) -> bool:
        return self.path.exists() and any(self.path.glob("*.wav"))


def list_voices() -> list[Voice]:
    """List all available voices."""
    ensure_dirs()
    voices = []
    if VOICES_DIR.exists():
        for d in sorted(VOICES_DIR.iterdir()):
            if d.is_dir() and any(d.glob("*.wav")):
                voices.append(Voice(name=d.name, path=d))
    return voices


def get_voice(name: str) -> Voice:
    """Get a voice by name."""
    voice = Voice(name=name, path=VOICES_DIR / name)
    if not voice.exists:
        raise FileNotFoundError(f"Voice '{name}' not found at {voice.path}")
    return voice


def add_voice(name: str, wav_source: Path) -> Voice:
    """Add a new voice from a WAV file."""
    ensure_dirs()
    voice_dir = VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)
    dest = voice_dir / wav_source.name
    shutil.copy2(wav_source, dest)
    return Voice(name=name, path=voice_dir)
