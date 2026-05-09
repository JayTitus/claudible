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


def _migrate(data: dict) -> None:
    """Migrate old config keys to current schema."""
    rephrase = data.get("rephrase", {})
    # ollama_url → api_url (added in v0.3)
    if "ollama_url" in rephrase and "api_url" not in rephrase:
        url = rephrase.pop("ollama_url")
        rephrase["api_url"] = url.rstrip("/") + "/v1"
    elif "ollama_url" in rephrase:
        del rephrase["ollama_url"]
    # Clean up bogus model values from old TUI bug
    if rephrase.get("model", "").startswith("Select."):
        del rephrase["model"]


class TTSConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 5959
    model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    voice: str = "default"
    language: str = "en"
    speed: float = 1.0
    voices_dir: str = ""  # empty = default VOICES_DIR
    audio_lead_in_ms: int = 150  # silence prepended to audio (helps Bluetooth sinks)


class STTConfig(BaseModel):
    nerd_dictation_path: str = "nerd-dictation"
    vosk_model: str = "small"
    push_to_talk_key: str = "KEY_RIGHTCTRL"
    hold_mode: bool = True
    toggle_key: str = "KEY_SCROLLLOCK"
    noise_suppression: bool = False
    rnnoise_vad_threshold: int = 70  # RNNoise VAD threshold (0-99, higher = more aggressive)
    rnnoise_vad_grace_ms: int = 200  # Grace period after VAD drops before silence gate
    rnnoise_retroactive_ms: int = 100  # Include audio just before VAD triggered
    echo_cancellation: bool = False
    wakeword_enabled: bool = False
    wakeword_timeout: float = 15.0
    window_lock_enabled: bool = True
    watched_processes: list[str] = Field(default_factory=lambda: ["claude", "codex", "gemini"])
    process_watch_interval: float = 2.0
    # Silero VAD pre-filter (rejects non-speech audio before VOSK)
    vad_enabled: bool = False
    vad_threshold: float = 0.5  # 0..1, higher = stricter (more rejected)
    vad_min_speech_ms: int = 200  # require this much continuous speech to start
    vad_min_silence_ms: int = 300  # silence needed to end an utterance
    vad_speech_pad_ms: int = 100  # audio kept before speech start, in ms


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
    trigger_words: dict[str, str] = Field(default_factory=dict)  # persona → trigger word
    trigger_modes: dict[str, str] = Field(default_factory=dict)  # persona → "always"|"ptt" (default: always)
    persona_voices: dict[str, str] = Field(default_factory=dict)  # persona → voice name


class CorrectionConfig(BaseModel):
    enabled: bool = True
    api_url: str = ""  # empty = use container or default Ollama
    model: str = "qwen2.5:3b"  # best instruction compliance for STT correction
    timeout_ms: int = 2000
    log_enabled: bool = True


class ContainerConfig(BaseModel):
    managed: bool = False
    gpu: bool = True
    correction_model: str = "llama3.2:1b"
    rephrase_model: str = "llama3.2:3b"
    port: int = 11435


class CompletionConfig(BaseModel):
    mode: str = "none"  # "none" / "simple" / "persona"
    simple_phrase: str = "Done."
    persona_prefix: str = ""
    max_tokens: int = 60
    temperature: float = 0.9


class HookConfig(BaseModel):
    mode: str = "full"  # "full" / "questions" / "completion" / "off"


class Config(BaseModel):
    tts: TTSConfig = Field(default_factory=TTSConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    dictation: DictationConfig = Field(default_factory=DictationConfig)
    rephrase: RephraseConfig = Field(default_factory=RephraseConfig)
    correction: CorrectionConfig = Field(default_factory=CorrectionConfig)
    container: ContainerConfig = Field(default_factory=ContainerConfig)
    completion: CompletionConfig = Field(default_factory=CompletionConfig)
    hook: HookConfig = Field(default_factory=HookConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Load config from TOML file, falling back to defaults."""
        path = path or CONFIG_FILE
        if path.exists():
            with open(path, "rb") as f:
                data = tomllib.load(f)
            _migrate(data)
            return cls.model_validate(data)
        return cls()

    def save(self, path: Path | None = None) -> None:
        """Write current config to TOML file."""
        path = path or CONFIG_FILE
        ensure_dirs()
        with open(path, "wb") as f:
            tomli_w.dump(self.model_dump(), f)
