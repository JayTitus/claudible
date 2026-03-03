"""Install bundled persona voices to the user's voices directory."""

from __future__ import annotations

import importlib.resources
import logging
import shutil
from pathlib import Path

from claudible.paths import VOICES_DIR

log = logging.getLogger(__name__)

# Default persona → voice mapping
PERSONA_VOICES: dict[str, str] = {
    "default": "default-male",
    "jarvis": "jarvis",
    "casual": "casual",
    "terse": "terse",
    "mission-control": "mission-control",
    "noir": "noir",
    "butler": "butler",
    "pirate": "pirate",
    "drill-sergeant": "drill-sergeant",
    "announcer": "announcer",
    "oracle": "oracle",
    "engineer": "engineer",
}


def list_bundled_voices() -> list[str]:
    """List voice names bundled with the package."""
    data_dir = importlib.resources.files("claudible.data") / "voices"
    path = Path(str(data_dir))
    if not path.is_dir():
        return []
    return sorted(
        d.name for d in path.iterdir()
        if d.is_dir() and any(d.glob("*.wav"))
    )


def install_bundled_voices(force: bool = False) -> list[str]:
    """Copy bundled voices to ~/.local/share/claudible/voices/.

    Returns list of voice names installed. Skips voices that already exist
    unless force=True.
    """
    data_dir = importlib.resources.files("claudible.data") / "voices"
    src_path = Path(str(data_dir))
    if not src_path.is_dir():
        log.warning("No bundled voices found at %s", src_path)
        return []

    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    installed = []

    for voice_dir in sorted(src_path.iterdir()):
        if not voice_dir.is_dir():
            continue
        wavs = list(voice_dir.glob("*.wav"))
        if not wavs:
            continue

        name = voice_dir.name
        dest = VOICES_DIR / name

        if dest.exists() and not force:
            log.debug("Voice '%s' already exists, skipping", name)
            continue

        dest.mkdir(parents=True, exist_ok=True)
        for wav in wavs:
            shutil.copy2(wav, dest / wav.name)
        installed.append(name)
        log.info("Installed voice: %s", name)

    return installed


def setup_persona_voice_defaults() -> dict[str, str]:
    """Return the default persona→voice mapping, only for voices that exist."""
    available = set()
    if VOICES_DIR.exists():
        available = {d.name for d in VOICES_DIR.iterdir() if d.is_dir() and any(d.glob("*.wav"))}

    return {
        persona: voice
        for persona, voice in PERSONA_VOICES.items()
        if voice in available
    }
