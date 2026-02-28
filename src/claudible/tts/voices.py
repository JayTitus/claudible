"""Voice management — discovering, adding, validating, and processing voice profiles."""

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


def _resolve_dir(voices_dir: str | Path | None = None) -> Path:
    """Resolve the voices directory, falling back to the default."""
    if voices_dir and str(voices_dir).strip():
        return Path(voices_dir).expanduser()
    return VOICES_DIR


def list_voices(voices_dir: str | Path | None = None) -> list[Voice]:
    """List all available voices."""
    ensure_dirs()
    vdir = _resolve_dir(voices_dir)
    voices = []
    if vdir.exists():
        for d in sorted(vdir.iterdir()):
            if d.is_dir() and any(d.glob("*.wav")):
                voices.append(Voice(name=d.name, path=d))
    return voices


def get_voice(name: str, voices_dir: str | Path | None = None) -> Voice:
    """Get a voice by name."""
    vdir = _resolve_dir(voices_dir)
    voice = Voice(name=name, path=vdir / name)
    if not voice.exists:
        raise FileNotFoundError(f"Voice '{name}' not found at {voice.path}")
    return voice


def add_voice(name: str, wav_source: Path) -> Voice:
    """Add a new voice from a WAV file (no validation/processing)."""
    ensure_dirs()
    voice_dir = VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)
    dest = voice_dir / wav_source.name
    shutil.copy2(wav_source, dest)
    return Voice(name=name, path=voice_dir)


def validate_voice_sample(path: Path) -> list[str]:
    """Validate a voice sample file. Returns list of warnings/errors.

    Empty list = all good. Strings starting with "ERROR:" are fatal.
    """
    import soundfile as sf

    issues: list[str] = []

    if not path.exists():
        return ["ERROR: File does not exist"]
    if not path.is_file():
        return ["ERROR: Path is not a file"]

    try:
        info = sf.info(str(path))
    except Exception as e:
        return [f"ERROR: Cannot read audio file: {e}"]

    duration = info.duration
    if duration < 6:
        issues.append(f"ERROR: Sample too short ({duration:.1f}s). Need at least 6 seconds.")
    elif duration > 30:
        issues.append(f"Warning: Sample is long ({duration:.1f}s). 6-30 seconds is ideal.")

    if info.samplerate != 22050:
        issues.append(
            f"Warning: Sample rate is {info.samplerate} Hz (will resample to 22050 Hz)."
        )

    if info.channels > 1:
        issues.append(
            f"Warning: Audio has {info.channels} channels (will convert to mono)."
        )

    return issues


def process_voice_sample(source: Path, name: str) -> Voice:
    """Validate, resample to 22050 Hz mono WAV, and install as a voice.

    Raises ValueError if validation finds fatal errors.
    """
    import numpy as np
    import soundfile as sf

    issues = validate_voice_sample(source)
    errors = [i for i in issues if i.startswith("ERROR:")]
    if errors:
        raise ValueError("\n".join(errors))

    # Read the audio
    data, sr = sf.read(str(source), dtype="float32")

    # Convert to mono if needed
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    # Resample if needed
    if sr != 22050:
        # Simple linear interpolation resampling
        duration = len(data) / sr
        new_length = int(duration * 22050)
        indices = np.linspace(0, len(data) - 1, new_length)
        data = np.interp(indices, np.arange(len(data)), data)
        sr = 22050

    # Write to voice directory
    ensure_dirs()
    voice_dir = VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)
    dest = voice_dir / "sample.wav"
    sf.write(str(dest), data, sr, subtype="PCM_16")

    return Voice(name=name, path=voice_dir)


def combine_samples(
    sources: list[Path],
    name: str,
    *,
    target_duration: float = 15.0,
    silence_gap: float = 0.5,
) -> Voice:
    """Combine multiple short audio clips into a single XTTS-ready voice sample.

    Selects the longest clips first until target_duration is reached.
    Inserts silence_gap seconds between clips. Resamples to 22050 Hz mono.
    """
    import numpy as np
    import soundfile as sf

    if not sources:
        raise ValueError("No source files provided")

    # Read and score all clips by duration (longest first = best for XTTS)
    clips: list[tuple[float, np.ndarray]] = []
    for src in sources:
        try:
            data, sr = sf.read(str(src), dtype="float32")
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            # Resample to 22050 if needed
            if sr != 22050:
                duration = len(data) / sr
                new_length = int(duration * 22050)
                indices = np.linspace(0, len(data) - 1, new_length)
                data = np.interp(indices, np.arange(len(data)), data)
            clips.append((len(data) / 22050, data))
        except Exception:
            continue

    if not clips:
        raise ValueError("Could not read any audio files")

    # Sort by duration descending — longer clips are better quality references
    clips.sort(key=lambda x: x[0], reverse=True)

    # Build combined audio up to target_duration
    silence = np.zeros(int(silence_gap * 22050), dtype=np.float32)
    combined: list[np.ndarray] = []
    total = 0.0

    for dur, data in clips:
        if total + dur > target_duration and combined:
            break
        if combined:
            combined.append(silence)
            total += silence_gap
        combined.append(data)
        total += dur

    audio = np.concatenate(combined)

    # Normalize peak to -1 dB
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (0.89 / peak)

    # Write
    ensure_dirs()
    voice_dir = VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)
    dest = voice_dir / "sample.wav"
    sf.write(str(dest), audio, 22050, subtype="PCM_16")

    return Voice(name=name, path=voice_dir)


def get_voice_info(name: str, voices_dir: str | Path | None = None) -> dict:
    """Get info about a voice sample (duration, sample rate, file size)."""
    import soundfile as sf

    voice = get_voice(name, voices_dir=voices_dir)
    wav = voice.wav_file
    info = sf.info(str(wav))
    return {
        "name": name,
        "path": str(wav),
        "duration": round(info.duration, 1),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "file_size_kb": round(wav.stat().st_size / 1024, 1),
    }
