"""Wrapper around nerd-dictation for speech-to-text."""

from __future__ import annotations

import logging
import os
import shutil
import site
import subprocess
import sys

from claudible.config import Config

log = logging.getLogger(__name__)


def _build_pythonpath() -> str:
    """Build a PYTHONPATH that lets nerd-dictation find vosk from our venv.

    nerd-dictation uses ``#!/usr/bin/env python3`` which may resolve to a
    system Python that doesn't have vosk.  We export our site-packages so
    the subprocess can ``import vosk`` regardless of which interpreter runs.
    """
    paths: list[str] = []
    # Add our venv's site-packages directories
    for p in site.getsitepackages():
        if p not in paths:
            paths.append(p)
    # Also include the user site if relevant
    user_site = site.getusersitepackages()
    if isinstance(user_site, str) and user_site not in paths:
        paths.append(user_site)

    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        paths.append(existing)
    return os.pathsep.join(paths)


class Dictation:
    """Manages nerd-dictation subprocess for STT."""

    def __init__(self, config: Config | None = None):
        cfg = config or Config.load()
        self._bin = cfg.stt.nerd_dictation_path
        self._model = cfg.stt.vosk_model
        self._noise_suppression = cfg.stt.noise_suppression
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

        # Ensure nerd-dictation callback script is current
        try:
            from claudible.stt.callback import generate_callback

            generate_callback()
        except Exception:
            log.debug("Failed to generate nerd-dictation callback", exc_info=True)

        model_dir = self._model_path
        cmd = [self._bin, "begin", "--continuous", "--vosk-model-dir", model_dir]

        # Use RNNoise-filtered virtual mic when noise suppression is on
        if self._noise_suppression:
            cmd.extend(["--pulse-device-name", "effect_output.rnnoise"])
            log.info("Noise suppression enabled — using RNNoise virtual source")

        log.info("Starting nerd-dictation: %s", " ".join(cmd))

        # Pass our site-packages via PYTHONPATH so nerd-dictation can find vosk
        env = os.environ.copy()
        env["PYTHONPATH"] = _build_pythonpath()

        self._process = subprocess.Popen(
            cmd,
            env=env,
            stderr=subprocess.PIPE,
        )
        # Check if it died immediately (e.g. missing model)
        try:
            self._process.wait(timeout=1.0)
            # If we get here, the process exited already
            stderr = self._process.stderr.read().decode(errors="replace").strip() if self._process.stderr else ""
            log.error("nerd-dictation exited immediately (code %d): %s", self._process.returncode, stderr)
            self._process = None
        except subprocess.TimeoutExpired:
            # Still running — good
            pass

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
