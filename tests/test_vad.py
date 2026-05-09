"""Tests for Silero VAD wrapper."""

from __future__ import annotations

import numpy as np
import pytest

from claudible.stt.vad import SileroVAD, SpeechGate, int16_to_float32


SR = 16000


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def _white_noise(seconds: float, amplitude: float = 0.02) -> np.ndarray:
    """Low-amplitude white noise — should NOT register as speech."""
    rng = np.random.default_rng(42)
    return (rng.standard_normal(int(seconds * SR)) * amplitude).astype(np.float32)


def _formant_tone(seconds: float, f0: float = 150.0) -> np.ndarray:
    """Synthesize a vowel-like waveform with multiple harmonics.

    A pure sine wave isn't reliably classified as speech by Silero VAD;
    we need formant-like structure with several harmonics.
    """
    t = np.linspace(0, seconds, int(seconds * SR), endpoint=False, dtype=np.float32)
    # f0 + 2 formants typical of /a/ vowel
    formants = [f0, 730, 1090, 2440]
    amps = [0.4, 0.3, 0.2, 0.1]
    sig = sum(a * np.sin(2 * np.pi * f * t) for a, f in zip(amps, formants))
    # Tremolo to make it sound more speech-like
    tremolo = 0.5 + 0.5 * np.sin(2 * np.pi * 5 * t)
    sig = sig * tremolo
    return sig.astype(np.float32) * 0.5


def test_vad_silence_low_probability():
    """Silence should produce very low speech probability."""
    vad = SileroVAD(sample_rate=SR)
    silence = _silence(1.0)
    probs = []
    for i in range(0, len(silence) - vad.window_samples, vad.window_samples):
        probs.append(vad.predict(silence[i:i + vad.window_samples]))
    assert max(probs) < 0.3, f"silence got too-high p={max(probs):.3f}"


def test_vad_white_noise_low_probability():
    """Low-amplitude white noise should be rejected."""
    vad = SileroVAD(sample_rate=SR)
    noise = _white_noise(1.0, amplitude=0.02)
    probs = []
    for i in range(0, len(noise) - vad.window_samples, vad.window_samples):
        probs.append(vad.predict(noise[i:i + vad.window_samples]))
    # A few windows may spike but the median should be low
    assert sorted(probs)[len(probs) // 2] < 0.5


def test_vad_state_resets():
    """reset() should restore initial behavior."""
    vad = SileroVAD(sample_rate=SR)
    sig = _formant_tone(0.5)
    for i in range(0, len(sig) - vad.window_samples, vad.window_samples):
        vad.predict(sig[i:i + vad.window_samples])

    state_before = vad._state.copy()
    vad.reset()
    assert not np.array_equal(state_before, vad._state)
    assert np.all(vad._state == 0)


def test_vad_window_size_validation():
    vad = SileroVAD(sample_rate=SR)
    with pytest.raises(ValueError, match="expected"):
        vad.predict(np.zeros(100, dtype=np.float32))


def test_vad_invalid_sample_rate():
    with pytest.raises(ValueError, match="8000 or 16000"):
        SileroVAD(sample_rate=44100)


def test_int16_conversion_roundtrip():
    """int16 bytes → float32 should preserve waveform shape."""
    samples = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)
    floats = int16_to_float32(samples.tobytes())
    assert floats.shape == (5,)
    assert -1.0 <= floats.min() and floats.max() <= 1.0
    assert abs(floats[1] - 0.5) < 0.001
    assert abs(floats[2] - (-0.5)) < 0.001


# --- SpeechGate behavior ---


def test_gate_silence_no_events():
    """Pure silence should never trigger speech_start."""
    gate = SpeechGate(threshold=0.5, min_speech_ms=100)
    events = gate.feed(_silence(2.0))
    assert all(e.event != "speech_start" for e in events)
    assert all(not e.is_speech for e in events)


def test_gate_in_speech_flag_resets():
    gate = SpeechGate(threshold=0.5)
    gate.feed(_silence(0.5))
    assert not gate.is_in_speech


def test_gate_pad_buffers_silence_before_speech():
    """The pre-roll pad should hold a few windows of silence."""
    gate = SpeechGate(threshold=0.5, speech_pad_ms=100)
    # Feed silence — pad should be filling
    events = gate.feed(_silence(0.5))
    assert len(gate._pad) > 0
    assert all(e.audio is None for e in events if not e.is_speech)


def test_gate_reset_clears_state():
    gate = SpeechGate(threshold=0.5)
    gate.feed(_white_noise(0.5))
    gate._in_speech = True
    gate._above_count = 99
    gate.reset()
    assert not gate.is_in_speech
    assert gate._above_count == 0
    assert len(gate._buffer) == 0


def test_gate_partial_buffer_carries_over():
    """Audio shorter than one window should be buffered, not dropped."""
    gate = SpeechGate(threshold=0.5)
    short_chunk = _silence(0.005)  # 80 samples — shorter than 512 window
    events = gate.feed(short_chunk)
    assert len(events) == 0
    assert len(gate._buffer) == len(short_chunk)


def test_gate_processes_chunks_streaming():
    """Splitting audio across multiple feed() calls = single big call."""
    gate1 = SpeechGate(threshold=0.5)
    gate2 = SpeechGate(threshold=0.5)
    audio = _silence(1.0)

    one_shot = gate1.feed(audio)
    streamed: list = []
    for chunk_start in range(0, len(audio), 800):
        streamed.extend(gate2.feed(audio[chunk_start:chunk_start + 800]))

    assert len(one_shot) == len(streamed)
    for a, b in zip(one_shot, streamed):
        assert a.event == b.event
        assert abs(a.probability - b.probability) < 1e-5


def test_gate_int16_input():
    """Gate should accept raw int16 PCM bytes as well as float arrays."""
    gate = SpeechGate(threshold=0.5)
    silence_int16 = np.zeros(SR, dtype=np.int16).tobytes()
    events = gate.feed(silence_int16)
    assert len(events) > 0
    assert all(not e.is_speech for e in events)
