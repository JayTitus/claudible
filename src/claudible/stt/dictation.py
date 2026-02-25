"""Wrapper around nerd-dictation for speech-to-text."""

from __future__ import annotations

import logging
import shutil
import subprocess

from claudible.config import Config

log = logging.getLogger(__name__)


class Dictation:
    """Manages nerd-dictation subprocess for STT."""

    def __init__(self, config: Config | None = None):
        cfg = config or Config.load()
        self._bin = cfg.stt.nerd_dictation_path
        self._model = cfg.stt.vosk_model
        self._process: subprocess.Popen | None = None

    @property
    def is_available(self) -> bool:
        """Check if nerd-dictation is installed."""
        return shutil.which(self._bin) is not None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Start nerd-dictation in begin mode (types into focused window)."""
        if self.is_running:
            log.warning("nerd-dictation already running")
            return

        if not self.is_available:
            raise RuntimeError(
                f"nerd-dictation not found at '{self._bin}'. "
                "Install it: https://github.com/ideasman42/nerd-dictation"
            )

        cmd = [self._bin, "begin", "--vosk-model-dir", self._model_path]
        log.info("Starting nerd-dictation: %s", " ".join(cmd))
        self._process = subprocess.Popen(cmd)

    def stop(self) -> None:
        """Stop nerd-dictation."""
        if not self.is_running:
            return
        subprocess.run([self._bin, "end"], check=False)
        self._process = None

    @property
    def _model_path(self) -> str:
        """Resolve the VOSK model path."""
        from pathlib import Path

        # Check common locations
        candidates = [
            Path.home() / ".local" / "share" / "nerd-dictation" / self._model,
            Path.home() / ".local" / "share" / "vosk" / self._model,
            Path(f"/usr/share/vosk/{self._model}"),
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        # Fall back to the raw value (user might have set an absolute path)
        return self._model
