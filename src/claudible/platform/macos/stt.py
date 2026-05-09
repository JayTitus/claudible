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

        log.info("VOSK dictation started (model=%s)", self._model_name)

        try:
            with sd.RawInputStream(
                samplerate=samplerate, blocksize=8000, dtype="int16",
                channels=1, callback=None,
            ) as stream:
                while not self._stop_event.is_set():
                    data = stream.read(4000)[0]
                    if rec.AcceptWaveform(bytes(data)):
                        result = json.loads(rec.Result())
                        text = result.get("text", "").strip()
                        if text:
                            self._on_text(text)
        except Exception:
            log.exception("VOSK dictation error")
        finally:
            self._running = False
            log.info("VOSK dictation stopped")

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
