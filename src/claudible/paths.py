"""XDG-compliant paths for claudible data, config, and cache."""

from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "claudible"
DATA_DIR = Path.home() / ".local" / "share" / "claudible"
CACHE_DIR = Path.home() / ".cache" / "claudible"

VOICES_DIR = DATA_DIR / "voices"
EMBEDDINGS_DIR = CACHE_DIR / "embeddings"
CONFIG_FILE = CONFIG_DIR / "config.toml"
TTS_MUTE_FLAG = CACHE_DIR / "tts_muted"


def ensure_dirs() -> None:
    """Create all required directories."""
    for d in (CONFIG_DIR, DATA_DIR, VOICES_DIR, EMBEDDINGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
