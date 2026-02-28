"""Configuration management — TOML-based with sensible defaults."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

from claudible.paths import CONFIG_FILE, ensure_dirs

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w


class TTSConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 5959
    model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    voice: str = "default"
    language: str = "en"
    speed: float = 1.0
    voices_dir: str = ""  # empty = default VOICES_DIR


class STTConfig(BaseModel):
    nerd_dictation_path: str = "nerd-dictation"
    vosk_model: str = "small"
    push_to_talk_key: str = "KEY_RIGHTCTRL"
    hold_mode: bool = True
    toggle_key: str = "KEY_SCROLLLOCK"
    noise_suppression: bool = False


class DictationConfig(BaseModel):
    """Voice keyword → keystroke mappings for nerd-dictation."""

    keywords: dict[str, str] = Field(default_factory=lambda: {
        "submit": "Return",
        "enter": "Return",
        "backspace": "BackSpace",
        "tab": "Tab",
        "escape": "Escape",
    })


class RephraseConfig(BaseModel):
    enabled: bool = False
    api_url: str = "http://localhost:11434/v1"
    api_key: str = ""  # optional — needed for Open WebUI or hosted providers
    model: str = "llama3.2:3b"
    persona: str = "default"


class Config(BaseModel):
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    dictation: DictationConfig = Field(default_factory=DictationConfig)
    rephrase: RephraseConfig = Field(default_factory=RephraseConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load config from TOML file, falling back to defaults."""
        path = path or CONFIG_FILE
        if path.exists():
            with open(path, "rb") as f:
                data = tomllib.load(f)
            return cls.model_validate(data)
        return cls()

    def save(self, path: Path | None = None) -> None:
        """Write current config to TOML file."""
        path = path or CONFIG_FILE
        ensure_dirs()
        with open(path, "wb") as f:
            tomli_w.dump(self.model_dump(), f)
