"""Linux STT backend dispatch.

Selects between the legacy nerd-dictation subprocess and the new
in-process faster-whisper engine based on ``stt.engine`` in config.
"""

from __future__ import annotations

import logging
from typing import Any

from claudible.platform.base import STTBackend

log = logging.getLogger(__name__)


class LinuxSTT(STTBackend):
    """Dispatching backend — picks engine based on config.stt.engine."""

    def create_dictation(self, config: Any) -> Any:
        engine = getattr(config.stt, "engine", "nerd-dictation")
        if engine == "whisper":
            return _create_whisper(config)
        if engine == "nerd-dictation":
            return _create_nerd_dictation(config)
        log.warning("Unknown stt.engine=%r — falling back to nerd-dictation", engine)
        return _create_nerd_dictation(config)


# Backwards-compatible name retained so existing imports keep working.
NerdDictationSTT = LinuxSTT


def _create_nerd_dictation(config: Any) -> Any:
    from claudible.stt.dictation import Dictation

    return Dictation(config)


def _create_whisper(config: Any) -> Any:
    from claudible.platform.linux.inject import XdotoolInjector
    from claudible.stt.router import Router
    from claudible.stt.whisper_engine import WhisperEngine

    injector = XdotoolInjector()
    router = Router(config, injector)
    return WhisperEngine(config, router)
