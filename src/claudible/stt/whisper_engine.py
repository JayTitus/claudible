"""Streaming faster-whisper STT engine with Silero VAD.

Pipeline:

    sounddevice → SpeechGate (Silero VAD) → utterance buffer
                                          → faster-whisper.transcribe()
                                          → Router → Injector

Audio is captured on a sounddevice callback thread and pushed onto a
queue. A worker thread drains the queue, runs VAD, buffers speech
between speech_start and speech_end events, and sends the buffered
utterance to faster-whisper. The text comes back, gets routed via
:class:`~claudible.stt.router.Router`, and the buffer is reset.

The model is loaded once at start time (≈20 s on GPU) and reused for
every utterance. Transcription itself is sub-second on a consumer
GPU for utterances under 30 s.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

import numpy as np

from claudible.config import Config
from claudible.stt.router import Router, RouterResult
from claudible.stt.vad import SpeechGate

log = logging.getLogger(__name__)


def _resolve_compute_type(device: str, compute_type: str) -> str:
    """Pick a sensible compute_type when set to "auto"."""
    if compute_type != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


def _resolve_device(device: str) -> str:
    """Pick cuda when available and requested, else cpu."""
    if device == "cuda":
        return "cuda"
    if device == "cpu":
        return "cpu"
    # auto
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _is_hallucination(text: str, blocked: list[str]) -> bool:
    """Return True if text matches a known hallucination phrase."""
    lower = text.strip().lower()
    if not lower:
        return True
    return any(p in lower for p in blocked)


class WhisperEngine:
    """Long-running streaming STT engine.

    Compatible with the existing Dictation API used by the tray:
    ``is_available`` / ``is_running`` / ``start()`` / ``stop()``.
    """

    def __init__(self, config: Config, router: Router) -> None:
        self._config = config
        self._router = router
        self._running = False
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)
        self._model: Any | None = None
        self._gate: SpeechGate | None = None
        self._utterance: list[np.ndarray] = []
        self._utt_lock = threading.Lock()

    @property
    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            import sounddevice  # noqa: F401
            from claudible.stt.vad import MODEL_PATH

            return MODEL_PATH.exists()
        except ImportError:
            return False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            log.warning("WhisperEngine already running")
            return
        if not self.is_available:
            raise RuntimeError(
                "faster-whisper / sounddevice / Silero VAD not installed"
            )

        self._stop_event.clear()
        self._running = True
        self._worker = threading.Thread(
            target=self._run, name="whisper-stt", daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        self._running = False
        if self._worker:
            self._worker.join(timeout=5)
            self._worker = None

    # ── Worker ──────────────────────────────────────────────────────────

    def _load_model(self):
        from faster_whisper import WhisperModel

        wcfg = self._config.whisper
        device = _resolve_device(wcfg.device)
        compute_type = _resolve_compute_type(device, wcfg.compute_type)

        log.info("Loading faster-whisper model=%s device=%s compute_type=%s",
                 wcfg.model, device, compute_type)
        t0 = time.time()
        model = WhisperModel(wcfg.model, device=device, compute_type=compute_type)
        log.info("faster-whisper loaded in %.1fs", time.time() - t0)
        return model

    def _run(self) -> None:
        try:
            self._model = self._load_model()
        except Exception:
            log.exception("Failed to load Whisper model")
            self._running = False
            return

        try:
            self._gate = SpeechGate(
                sample_rate=16000,
                threshold=self._config.stt.vad_threshold,
                min_speech_ms=self._config.stt.vad_min_speech_ms,
                min_silence_ms=self._config.stt.vad_min_silence_ms,
                speech_pad_ms=self._config.stt.vad_speech_pad_ms,
            )
        except Exception:
            log.exception("Failed to initialize Silero VAD")
            self._running = False
            return

        try:
            self._capture_loop()
        except Exception:
            log.exception("Whisper capture loop crashed")
        finally:
            self._running = False
            log.info("Whisper STT stopped")

    def _capture_loop(self) -> None:
        import sounddevice as sd

        wcfg = self._config.whisper

        def audio_callback(indata, frames, time_info, status):
            if status:
                log.debug("sounddevice status: %s", status)
            try:
                self._audio_q.put_nowait(indata[:, 0].copy())
            except queue.Full:
                # Drop on overrun rather than block the audio thread
                log.warning("audio queue full, dropping chunk")

        device_kwarg: dict = {}
        if wcfg.input_device:
            device_kwarg["device"] = wcfg.input_device

        log.info("Whisper STT listening (input_device=%r)",
                 wcfg.input_device or "default")

        with sd.InputStream(
            samplerate=16000, channels=1, dtype="float32",
            blocksize=1600, callback=audio_callback,  # 100 ms blocks
            **device_kwarg,
        ):
            while not self._stop_event.is_set():
                try:
                    chunk = self._audio_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                self._on_audio(chunk)

    def _on_audio(self, chunk: np.ndarray) -> None:
        assert self._gate is not None
        events = self._gate.feed(chunk)
        with self._utt_lock:
            for evt in events:
                if evt.event == "speech_start":
                    self._utterance = list(evt.pad)
                    if evt.audio is not None:
                        self._utterance.append(evt.audio)
                elif evt.is_speech and evt.audio is not None:
                    self._utterance.append(evt.audio)
                elif evt.event == "speech_end":
                    if evt.audio is not None:
                        self._utterance.append(evt.audio)
                    if self._utterance:
                        utt = np.concatenate(self._utterance)
                        self._utterance = []
                        # Run transcription off this thread so we don't
                        # block subsequent audio chunks
                        threading.Thread(
                            target=self._transcribe_and_route,
                            args=(utt,), daemon=True,
                        ).start()

    def _transcribe_and_route(self, audio: np.ndarray) -> None:
        assert self._model is not None
        wcfg = self._config.whisper
        try:
            t0 = time.time()
            segments, _info = self._model.transcribe(
                audio,
                language=wcfg.language,
                beam_size=wcfg.beam_size,
                condition_on_previous_text=wcfg.condition_on_previous_text,
                no_speech_threshold=wcfg.no_speech_threshold,
                log_prob_threshold=wcfg.log_prob_threshold,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            elapsed = time.time() - t0
        except Exception:
            log.exception("Whisper transcription failed")
            return

        if not text:
            log.debug("empty transcription (%.2fs audio)", len(audio) / 16000)
            return

        if _is_hallucination(text, wcfg.blocked_phrases):
            log.info("dropped hallucination: %r", text)
            return

        log.info("whisper: %r (%.2fs audio, %.2fs transcribe)",
                 text, len(audio) / 16000, elapsed)
        try:
            result: RouterResult = self._router.process(text)
            log.debug("router: %r", result)
        except Exception:
            log.exception("Router failed for text=%r", text)
