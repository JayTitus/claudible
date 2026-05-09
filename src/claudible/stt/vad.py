"""Silero VAD voice activity detection.

Wraps the Silero VAD ONNX model as a streaming-friendly speech gate.
Used to reject non-speech audio (vibrations, keyboard taps, ambient
noise) before it reaches the speech recognizer.

The model expects 512-sample windows at 16 kHz (32 ms) or 256-sample
windows at 8 kHz. Each call returns a probability in [0, 1] and
updates the model's hidden state.

A higher-level :class:`SpeechGate` adds hold/grace logic so brief dips
in confidence during a single utterance don't fragment a phrase.
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "models" / "silero_vad.onnx"

# Silero VAD requires fixed window sizes per sample rate
WINDOW_16K = 512
WINDOW_8K = 256


class SileroVAD:
    """Streaming Silero VAD wrapper.

    Maintains the model's recurrent state across chunks, so callers can
    feed continuous 16 kHz int16 audio and get a per-window probability
    of speech.
    """

    def __init__(self, sample_rate: int = 16000, model_path: Path | None = None) -> None:
        if sample_rate not in (8000, 16000):
            raise ValueError(f"Silero VAD supports 8000 or 16000 Hz, got {sample_rate}")

        try:
            import onnxruntime as ort
        except ImportError as e:
            raise ImportError(
                "onnxruntime is required for Silero VAD. "
                "Install with: pip install onnxruntime"
            ) from e

        path = model_path or MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"Silero VAD model not found at {path}. "
                "Re-install claudible or run `claudible vad install`."
            )

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(path), sess_options=opts, providers=["CPUExecutionProvider"],
        )
        self._sr = np.array(sample_rate, dtype=np.int64)
        self._window = WINDOW_16K if sample_rate == 16000 else WINDOW_8K
        self._reset_state()

    @property
    def window_samples(self) -> int:
        """Number of audio samples per inference call."""
        return self._window

    def _reset_state(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def reset(self) -> None:
        """Clear the recurrent state — call between independent utterances."""
        self._reset_state()

    def predict(self, samples: np.ndarray) -> float:
        """Run VAD on one window of float32 audio in [-1, 1].

        ``samples`` must contain exactly :attr:`window_samples` values.
        Returns the speech probability for this window.
        """
        if samples.shape != (self._window,):
            raise ValueError(
                f"expected ({self._window},) samples, got {samples.shape}"
            )
        inputs = {
            "input": samples.reshape(1, -1).astype(np.float32),
            "state": self._state,
            "sr": self._sr,
        }
        prob, new_state = self._session.run(["output", "stateN"], inputs)
        self._state = new_state
        return float(prob[0, 0])


def int16_to_float32(buf: bytes | np.ndarray) -> np.ndarray:
    """Convert little-endian int16 PCM to float32 in [-1, 1]."""
    if isinstance(buf, bytes):
        arr = np.frombuffer(buf, dtype=np.int16)
    else:
        arr = buf
    return arr.astype(np.float32) / 32768.0


class SpeechGate:
    """Stateful speech detector with hysteresis.

    Buffers incoming PCM into VAD-sized windows, tracks whether we are
    currently inside a speech segment, and emits "in speech" / "left
    speech" transitions with configurable thresholds and grace periods.

    Typical use:

        gate = SpeechGate()
        for chunk in audio_stream:
            for status in gate.feed(chunk):
                if status.is_speech:
                    feed_chunk_to_recognizer(status.audio)
                elif status.event == "speech_end":
                    finalize_recognizer()
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_speech_ms: int = 200,
        min_silence_ms: int = 200,
        speech_pad_ms: int = 100,
        model_path: Path | None = None,
    ) -> None:
        self._vad = SileroVAD(sample_rate=sample_rate, model_path=model_path)
        self._sr = sample_rate
        self._threshold = threshold
        self._window_ms = self._vad.window_samples * 1000 / sample_rate
        self._min_speech_windows = max(1, int(min_speech_ms / self._window_ms))
        self._min_silence_windows = max(1, int(min_silence_ms / self._window_ms))
        self._pad_windows = max(0, int(speech_pad_ms / self._window_ms))

        self._buffer = np.empty(0, dtype=np.float32)
        self._in_speech = False
        self._above_count = 0
        self._below_count = 0
        # Pre-buffer recent silence so we don't clip the start of speech
        self._pad: deque[np.ndarray] = deque(maxlen=self._pad_windows)

    @property
    def is_in_speech(self) -> bool:
        return self._in_speech

    @property
    def threshold(self) -> float:
        return self._threshold

    def reset(self) -> None:
        """Clear all state — call when stopping/restarting capture."""
        self._vad.reset()
        self._buffer = np.empty(0, dtype=np.float32)
        self._in_speech = False
        self._above_count = 0
        self._below_count = 0
        self._pad.clear()

    def feed(self, pcm: bytes | np.ndarray) -> list[VadEvent]:
        """Process a chunk of audio and return any state transitions.

        ``pcm`` may be int16 bytes/array or float32 array. Returns a
        list of :class:`VadEvent` items — one per VAD window processed,
        in chronological order. Callers that don't need per-window
        granularity can ignore events with ``event == "continue"``.
        """
        if isinstance(pcm, bytes):
            samples = int16_to_float32(pcm)
        elif pcm.dtype == np.int16:
            samples = int16_to_float32(pcm)
        else:
            samples = pcm.astype(np.float32, copy=False)

        self._buffer = np.concatenate([self._buffer, samples])
        events: list[VadEvent] = []
        win = self._vad.window_samples

        while len(self._buffer) >= win:
            window = self._buffer[:win].copy()
            self._buffer = self._buffer[win:]
            prob = self._vad.predict(window)
            event = self._step(window, prob)
            events.append(event)

        return events

    def _step(self, window: np.ndarray, prob: float) -> VadEvent:
        if prob >= self._threshold:
            self._above_count += 1
            self._below_count = 0
            if not self._in_speech and self._above_count >= self._min_speech_windows:
                self._in_speech = True
                # Emit padding frames so the recognizer gets the start of speech
                pad = list(self._pad)
                self._pad.clear()
                return VadEvent(
                    event="speech_start",
                    is_speech=True,
                    probability=prob,
                    audio=window,
                    pad=pad,
                )
            if self._in_speech:
                return VadEvent(
                    event="continue",
                    is_speech=True,
                    probability=prob,
                    audio=window,
                )
            # Below the start-debounce: still buffering
            self._pad.append(window)
            return VadEvent(
                event="continue",
                is_speech=False,
                probability=prob,
                audio=None,
            )

        # prob < threshold
        self._above_count = 0
        if self._in_speech:
            self._below_count += 1
            if self._below_count >= self._min_silence_windows:
                self._in_speech = False
                self._below_count = 0
                return VadEvent(
                    event="speech_end",
                    is_speech=False,
                    probability=prob,
                    audio=window,
                )
            # Still in speech (silence too short to end utterance)
            return VadEvent(
                event="continue",
                is_speech=True,
                probability=prob,
                audio=window,
            )

        self._pad.append(window)
        return VadEvent(
            event="continue",
            is_speech=False,
            probability=prob,
            audio=None,
        )


class VadEvent:
    """One VAD decision returned by :meth:`SpeechGate.feed`."""

    __slots__ = ("event", "is_speech", "probability", "audio", "pad")

    def __init__(
        self,
        event: str,
        is_speech: bool,
        probability: float,
        audio: np.ndarray | None,
        pad: list[np.ndarray] | None = None,
    ) -> None:
        self.event = event  # "speech_start" | "speech_end" | "continue"
        self.is_speech = is_speech
        self.probability = probability
        self.audio = audio
        self.pad = pad or []

    def __repr__(self) -> str:
        return (
            f"VadEvent(event={self.event!r}, is_speech={self.is_speech}, "
            f"p={self.probability:.3f})"
        )
