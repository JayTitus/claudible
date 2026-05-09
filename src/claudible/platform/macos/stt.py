"""macOS STT backend — direct VOSK via sounddevice.

Replaces nerd-dictation with an in-process VOSK recognizer, since
nerd-dictation depends on Linux-specific tools (xdotool, evdev).
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


class DirectVoskSTT(STTBackend):
    """Direct VOSK speech recognition using sounddevice."""

    def create_dictation(self, config: Any) -> Any:
        return MacOSDictation(config)


class MacOSDictation:
    """VOSK-based dictation for macOS — compatible with Dictation API."""

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

        model_path = self._resolve_model()
        if not model_path:
            log.error("VOSK model not found: %s", self._model_name)
            self._running = False
            return

        model = vosk.Model(model_path)
        samplerate = 16000
        rec = vosk.KaldiRecognizer(model, samplerate)

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
                    self._process_chunk(bytes(data), rec, gate)
        except Exception:
            log.exception("VOSK dictation error")
        finally:
            self._running = False
            log.info("VOSK dictation stopped")

    def _build_gate(self):
        """Build a SpeechGate if VAD is enabled, else None."""
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
            log.warning("Silero VAD unavailable, falling back to raw VOSK: %s", e)
            return None

    def _process_chunk(self, pcm: bytes, rec, gate) -> None:
        """Feed one audio chunk through the VAD gate (if any) into VOSK."""
        if gate is None:
            if rec.AcceptWaveform(pcm):
                self._emit_result(rec)
            return

        import numpy as np

        for evt in gate.feed(pcm):
            # Pad audio (pre-roll) on speech_start so VOSK gets utterance onset
            for pad_window in evt.pad:
                pad_pcm = (pad_window * 32768.0).astype(np.int16).tobytes()
                rec.AcceptWaveform(pad_pcm)

            if evt.is_speech and evt.audio is not None:
                window_pcm = (evt.audio * 32768.0).astype(np.int16).tobytes()
                if rec.AcceptWaveform(window_pcm):
                    self._emit_result(rec)
            elif evt.event == "speech_end":
                # Force VOSK to flush its buffered partial as a final result
                self._emit_result(rec, final=True)

    def _emit_result(self, rec, final: bool = False) -> None:
        """Read the current result from VOSK and dispatch text if any."""
        result_json = rec.FinalResult() if final else rec.Result()
        result = json.loads(result_json)
        text = result.get("text", "").strip()
        if text:
            self._on_text(text)

    def _on_text(self, text: str) -> None:
        """Handle recognized text — type into frontmost application."""
        try:
            from claudible.stt.processor import process_text

            processed = process_text(text, self._config)
            if processed:
                self._type_text(processed)
        except ImportError:
            # Fallback: type directly
            self._type_text(text)

    def _type_text(self, text: str) -> None:
        """Type text into the frontmost application using osascript."""
        try:
            # Escape for AppleScript
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'tell application "System Events" to keystroke "{escaped}"'],
                capture_output=True, timeout=3,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            log.debug("Failed to type text via osascript")

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
