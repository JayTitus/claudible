"""Cross-platform paths for claudible data, config, and cache.

Uses platformdirs for OS-appropriate directories. On Linux, output is identical
to the previous hardcoded XDG paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import platformdirs

CONFIG_DIR = Path(platformdirs.user_config_dir("claudible"))
DATA_DIR = Path(platformdirs.user_data_dir("claudible"))
CACHE_DIR = Path(platformdirs.user_cache_dir("claudible"))

VOICES_DIR = DATA_DIR / "voices"
EMBEDDINGS_DIR = CACHE_DIR / "embeddings"
OLLAMA_DATA_DIR = DATA_DIR / "ollama"
CONFIG_FILE = CONFIG_DIR / "config.toml"
TTS_MUTE_FLAG = CACHE_DIR / "tts_muted"
PID_FILE = CACHE_DIR / "claudible.pid"
WAKEWORD_STATE = CACHE_DIR / "wakeword.json"
WINDOW_STATE = CACHE_DIR / "windows.json"
STT_ACCURACY_LOG = CACHE_DIR / "stt_accuracy.jsonl"


def ensure_dirs() -> None:
    """Create all required directories."""
    for d in (CONFIG_DIR, DATA_DIR, VOICES_DIR, EMBEDDINGS_DIR, OLLAMA_DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)


def find_cudnn_lib() -> str | None:
    """Find the nvidia-cudnn library path inside the current Python environment."""
    try:
        import nvidia.cudnn

        # nvidia.cudnn may be a namespace package (__file__ is None), use __path__ instead
        for p in getattr(nvidia.cudnn, "__path__", []):
            cudnn_dir = Path(p) / "lib"
            if cudnn_dir.is_dir():
                return str(cudnn_dir)
    except ImportError:
        pass
    # Fallback: search site-packages
    for p in sys.path:
        candidate = Path(p) / "nvidia" / "cudnn" / "lib"
        if candidate.is_dir():
            return str(candidate)
    return None
