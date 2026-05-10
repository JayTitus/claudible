"""Tests for the Whisper streaming STT engine.

The Whisper model and sounddevice are heavy and require a GPU + a
mic, so these tests stub both. They verify the pipeline shape:

    audio chunks → SpeechGate → utterance buffer → fake Whisper
    → Router (FakeInjector) → recorded keystrokes
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from claudible.config import (
    Config,
    CorrectionConfig,
    DictationConfig,
    RephraseConfig,
    STTConfig,
    WhisperConfig,
)
from claudible.stt.router import Router
from claudible.stt.whisper_engine import WhisperEngine, _is_hallucination


class FakeWhisperSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeWhisperModel:
    """Stand-in for faster-whisper's WhisperModel."""

    def __init__(self, output_text: str = "hello world") -> None:
        self.output_text = output_text
        self.calls: list[np.ndarray] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(audio)
        return [FakeWhisperSegment(self.output_text)], None


class FakeInjector:
    def __init__(self):
        self.target = {}
        self.texts: list[str] = []
        self.keys: list[str] = []

    def set_target(self, t):
        self.target = t or {}

    def send_text(self, text):
        self.texts.append(text)
        return True

    def send_key(self, key):
        self.keys.append(key)
        return True

    def get_active_window(self):
        return None, ""

    def resolve_target(self, slot):
        return {}


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setattr("claudible.stt.router.WAKEWORD_STATE", tmp_path / "wake.json")
    monkeypatch.setattr("claudible.stt.router.WINDOW_STATE", tmp_path / "win.json")
    yield


def _config() -> Config:
    return Config(
        stt=STTConfig(
            wakeword_enabled=False,
            window_lock_enabled=False,
            vad_enabled=True,
            vad_threshold=0.5,
            vad_min_speech_ms=64,
            vad_min_silence_ms=100,
            vad_speech_pad_ms=64,
        ),
        whisper=WhisperConfig(model="tiny.en"),
        dictation=DictationConfig(keywords={"submit": "Return"}),
        rephrase=RephraseConfig(),
        correction=CorrectionConfig(enabled=False),
    )


# ─── Hallucination filter ─────────────────────────────────────────────────


def test_hallucination_filter_blocks_known_phrases():
    blocked = ["thanks for watching", "subtitles by"]
    assert _is_hallucination("Thanks for watching!", blocked)
    assert _is_hallucination("subtitles by xyz", blocked)
    assert not _is_hallucination("hello world", blocked)


def test_hallucination_filter_blocks_empty():
    assert _is_hallucination("", [])
    assert _is_hallucination("   ", [])


def test_hallucination_substring_match():
    blocked = ["amara.org"]
    assert _is_hallucination("Subtitles provided by Amara.org community", blocked)


# ─── Engine pipeline ─────────────────────────────────────────────────────


def _formant_audio(seconds: float = 0.5, f0: float = 150.0) -> np.ndarray:
    """Speech-like audio that Silero VAD will classify as speech."""
    sr = 16000
    t = np.linspace(0, seconds, int(seconds * sr), endpoint=False, dtype=np.float32)
    formants = [f0, 730, 1090, 2440]
    amps = [0.4, 0.3, 0.2, 0.1]
    sig = sum(a * np.sin(2 * np.pi * f * t) for a, f in zip(amps, formants))
    tremolo = 0.5 + 0.5 * np.sin(2 * np.pi * 5 * t)
    return (sig * tremolo * 0.5).astype(np.float32)


def _silence(seconds: float = 0.3) -> np.ndarray:
    return np.zeros(int(seconds * 16000), dtype=np.float32)


class StubGate:
    """Programmable VAD gate — emits whatever events you queue."""

    def __init__(self, scripted_events: list[list]) -> None:
        self._scripted = list(scripted_events)

    def feed(self, _chunk):
        if not self._scripted:
            return []
        return self._scripted.pop(0)


class FakeVadEvent:
    def __init__(self, event: str, audio: np.ndarray | None = None,
                 pad: list | None = None, is_speech: bool = False) -> None:
        self.event = event
        self.audio = audio
        self.pad = pad or []
        self.is_speech = is_speech
        self.probability = 1.0 if is_speech else 0.0


def test_engine_routes_transcription_via_router():
    """End-to-end: feed scripted VAD events, verify the fake Whisper
    output reaches the injector."""
    inj = FakeInjector()
    router = Router(_config(), inj)
    engine = WhisperEngine(_config(), router)
    engine._model = FakeWhisperModel(output_text="hello world")

    # Script: chunk 1 → speech_start, chunk 2 → continue, chunk 3 → speech_end
    win = np.ones(512, dtype=np.float32) * 0.1
    engine._gate = StubGate([
        [FakeVadEvent("speech_start", audio=win, pad=[win], is_speech=True)],
        [FakeVadEvent("continue", audio=win, is_speech=True)],
        [FakeVadEvent("speech_end", audio=win, is_speech=False)],
    ])

    for _ in range(3):
        engine._on_audio(np.zeros(1600, dtype=np.float32))

    # _transcribe_and_route runs in a daemon thread — give it a beat.
    deadline = time.time() + 2.0
    while not inj.texts and time.time() < deadline:
        time.sleep(0.05)

    assert inj.texts == ["hello world"]
    assert engine._model.calls, "model.transcribe should have been called"
    # Buffer should accumulate pad + start + continue + end = 4 windows
    assert len(engine._model.calls[0]) == 512 * 4


def test_engine_drops_empty_transcriptions():
    inj = FakeInjector()
    router = Router(_config(), inj)
    engine = WhisperEngine(_config(), router)
    engine._model = FakeWhisperModel(output_text="   ")  # whitespace only

    # Feed a synthetic utterance directly through the transcription helper
    audio = _formant_audio(1.0)
    engine._transcribe_and_route(audio)
    assert inj.texts == []


def test_engine_drops_hallucinations():
    inj = FakeInjector()
    router = Router(_config(), inj)
    engine = WhisperEngine(_config(), router)
    engine._model = FakeWhisperModel(output_text="Thanks for watching!")

    engine._transcribe_and_route(_formant_audio(1.0))
    assert inj.texts == []


def test_engine_silence_only_produces_no_routing():
    """No speech_end event → no transcription, no routing."""
    inj = FakeInjector()
    router = Router(_config(), inj)
    engine = WhisperEngine(_config(), router)
    engine._model = FakeWhisperModel()
    engine._gate = StubGate([
        # All "continue" with is_speech=False — VAD never sees speech start.
        [FakeVadEvent("continue", audio=None, is_speech=False)],
        [FakeVadEvent("continue", audio=None, is_speech=False)],
    ])

    for _ in range(2):
        engine._on_audio(np.zeros(1600, dtype=np.float32))

    time.sleep(0.2)
    assert engine._model.calls == []
    assert inj.texts == []


def test_is_running_lifecycle():
    engine = WhisperEngine(_config(), Router(_config(), FakeInjector()))
    assert not engine.is_running
    # Don't actually start (that would load the real model). Just verify
    # the flag is gated on _running, not on model presence.
    engine._running = True
    assert engine.is_running
    engine._running = False
    assert not engine.is_running
