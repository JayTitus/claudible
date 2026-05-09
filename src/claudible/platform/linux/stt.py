"""Linux STT backend — delegates to stt/dictation.py (nerd-dictation)."""

from __future__ import annotations

from typing import Any

from claudible.platform.base import STTBackend


class NerdDictationSTT(STTBackend):
    """nerd-dictation-based STT for Linux."""

    def create_dictation(self, config: Any) -> Any:
        from claudible.stt.dictation import Dictation

        return Dictation(config)
