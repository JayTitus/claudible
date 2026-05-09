"""Linux keyboard backend — delegates to stt/keybind.py (evdev)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from claudible.platform.base import KeyboardBackend


class EvdevKeyboard(KeyboardBackend):
    """evdev-based keyboard listener for PTT and toggle keys."""

    def run_ptt(self, config: Any) -> None:
        from claudible.stt.keybind import run_ptt

        run_ptt(config)

    def run_key_listener(
        self,
        config: Any,
        dictation: Any,
        continuous_on: Callable[[], None],
        continuous_off: Callable[[], None],
        stop_event: threading.Event,
        ptt_on: Callable[[], None] | None = None,
        ptt_off: Callable[[], None] | None = None,
        wake_state_changed: Callable[[str], None] | None = None,
        is_continuous: Callable[[], bool] | None = None,
    ) -> None:
        from claudible.stt.keybind import run_key_listener

        run_key_listener(
            config=config,
            dictation=dictation,
            continuous_on=continuous_on,
            continuous_off=continuous_off,
            stop_event=stop_event,
            ptt_on=ptt_on,
            ptt_off=ptt_off,
            wake_state_changed=wake_state_changed,
            is_continuous=is_continuous,
        )
