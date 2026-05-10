"""macOS STT backend.

Same architecture as Linux: dispatches based on ``stt.engine``. The
"whisper" engine is the recommended path; the legacy "vosk" option
remains for parity but Whisper is significantly more accurate.
nerd-dictation is not supported on macOS (it depends on evdev / X11),
so a config of ``stt.engine = "nerd-dictation"`` falls through to
the direct-VOSK implementation here.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Any

from claudible.platform.base import STTBackend

log = logging.getLogger(__name__)


class MacOSSTT(STTBackend):
    """Dispatching backend — picks engine based on config.stt.engine."""

    def create_dictation(self, config: Any) -> Any:
        engine = getattr(config.stt, "engine", "whisper")
        # nerd-dictation isn't a real option on macOS; treat it as a
        # request for the legacy direct-VOSK path.
        if engine in ("whisper",):
            return _create_whisper(config)
        if engine in ("vosk", "nerd-dictation", "direct"):
            return MacOSDictation(config)
        log.warning("Unknown stt.engine=%r — falling back to whisper", engine)
        return _create_whisper(config)


# Backwards-compatible name retained so existing imports keep working.
DirectVoskSTT = MacOSSTT


def _create_whisper(config: Any) -> Any:
    from claudible.platform.macos.inject import OsaScriptInjector
    from claudible.stt.router import Router
    from claudible.stt.whisper_engine import WhisperEngine

    injector = OsaScriptInjector()
    router = Router(config, injector)
    return WhisperEngine(config, router)


class MacOSDictation:
    """Legacy direct-VOSK dictation for macOS — kept for parity with
    the previous backend. New work should use the Whisper engine.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        self._model_name = config.stt.vosk_model
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_available(self) -> bool:
        try:
            import sounddevice  # noqa: F401
            import vosk  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            log.warning("VOSK dictation already running")
            return
        if not self.is_available:
            raise RuntimeError("VOSK or sounddevice not installed")
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="vosk-stt")
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        import sounddevice as sd
        import vosk

        from claudible.platform.macos.inject import OsaScriptInjector
        from claudible.stt.router import Router

        model_path = self._resolve_model()
        if not model_path:
            log.error("VOSK model not found: %s", self._model_name)
            self._running = False
            return

        model = vosk.Model(model_path)
        samplerate = 16000
        rec = vosk.KaldiRecognizer(model, samplerate)

        router = Router(self._config, OsaScriptInjector())

        gate = self._build_gate()
        if gate is not None:
            log.info("VOSK dictation started with Silero VAD pre-filter "
                     "(threshold=%.2f)", gate.threshold)
        else:
            log.info("VOSK dictation started (model=%s)", self._model_name)

        try:
            with sd.RawInputStream(
                samplerate=samplerate, blocksize=8000, dtype="int16",
                channels=1, callback=None,
            ) as stream:
                while not self._stop_event.is_set():
                    data = stream.read(4000)[0]
                    self._process_chunk(bytes(data), rec, gate, router)
        except Exception:
            log.exception("VOSK dictation error")
        finally:
            self._running = False
            log.info("VOSK dictation stopped")

    def _build_gate(self):
        if not getattr(self._config.stt, "vad_enabled", False):
            return None
        try:
            from claudible.stt.vad import SpeechGate

            return SpeechGate(
                sample_rate=16000,
                threshold=self._config.stt.vad_threshold,
                min_speech_ms=self._config.stt.vad_min_speech_ms,
                min_silence_ms=self._config.stt.vad_min_silence_ms,
                speech_pad_ms=self._config.stt.vad_speech_pad_ms,
            )
        except (ImportError, FileNotFoundError) as e:
            log.warning("Silero VAD unavailable: %s", e)
            return None

    def _process_chunk(self, pcm: bytes, rec, gate, router) -> None:
        if gate is None:
            if rec.AcceptWaveform(pcm):
                self._emit_result(rec, router)
            return

        import numpy as np

        for evt in gate.feed(pcm):
            for pad_window in evt.pad:
                pad_pcm = (pad_window * 32768.0).astype(np.int16).tobytes()
                rec.AcceptWaveform(pad_pcm)

            if evt.is_speech and evt.audio is not None:
                window_pcm = (evt.audio * 32768.0).astype(np.int16).tobytes()
                if rec.AcceptWaveform(window_pcm):
                    self._emit_result(rec, router)
            elif evt.event == "speech_end":
                self._emit_result(rec, router, final=True)

    def _emit_result(self, rec, router, final: bool = False) -> None:
        result_json = rec.FinalResult() if final else rec.Result()
        result = json.loads(result_json)
        text = result.get("text", "").strip()
        if text:
            try:
                router.process(text)
            except Exception:
                log.exception("Router failed for text=%r", text)

    def _resolve_model(self) -> str | None:
        candidates = [
            Path.home() / ".local" / "share" / "vosk" / self._model_name,
            Path.home() / "Library" / "Application Support" / "vosk" / self._model_name,
            Path(f"/usr/local/share/vosk/{self._model_name}"),
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None
