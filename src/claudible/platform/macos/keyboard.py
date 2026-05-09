"""macOS keyboard backend — pynput global hotkeys."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from pynput import keyboard

from claudible.platform.base import KeyboardBackend

log = logging.getLogger(__name__)


class PynputKeyboard(KeyboardBackend):
    """pynput-based keyboard listener for macOS."""

    # Map evdev key names to pynput Key objects
    _KEY_MAP = {
        "KEY_RIGHTCTRL": keyboard.Key.ctrl_r,
        "KEY_LEFTCTRL": keyboard.Key.ctrl_l,
        "KEY_SCROLLLOCK": keyboard.Key.scroll_lock,
        "KEY_F13": keyboard.Key.f13,
        "KEY_F14": keyboard.Key.f14,
        "KEY_F15": keyboard.Key.f15,
        "KEY_F16": keyboard.Key.f16,
        "KEY_F17": keyboard.Key.f17,
        "KEY_F18": keyboard.Key.f18,
        "KEY_F19": keyboard.Key.f19,
        "KEY_F20": keyboard.Key.f20,
    }

    def _resolve_key(self, key_name: str) -> keyboard.Key | keyboard.KeyCode | None:
        """Resolve an evdev-style key name to a pynput key."""
        if key_name in self._KEY_MAP:
            return self._KEY_MAP[key_name]
        # Try single character keys
        if key_name.startswith("KEY_") and len(key_name) == 5:
            return keyboard.KeyCode.from_char(key_name[-1].lower())
        log.warning("Unknown key for macOS: %s", key_name)
        return None

    def run_ptt(self, config: Any) -> None:
        ptt_key = self._resolve_key(config.stt.push_to_talk_key)
        if ptt_key is None:
            raise ValueError(f"Cannot map key: {config.stt.push_to_talk_key}")

        from claudible.stt.dictation import Dictation

        dictation = Dictation(config)
        if not dictation.is_available:
            raise RuntimeError("STT not available on this platform.")

        hold_mode = config.stt.hold_mode
        log.info("PTT listener started — %s %s", "hold" if hold_mode else "toggle", config.stt.push_to_talk_key)

        def on_press(key: Any) -> None:
            if key == ptt_key:
                if hold_mode:
                    dictation.start()
                elif not dictation.is_running:
                    dictation.start()
                else:
                    dictation.stop()

        def on_release(key: Any) -> None:
            if key == ptt_key and hold_mode:
                dictation.stop()

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                dictation.stop()
                log.info("PTT listener stopped")

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
        ptt_key = self._resolve_key(config.stt.push_to_talk_key)
        toggle_key = self._resolve_key(config.stt.toggle_key)

        if ptt_key is None and toggle_key is None:
            return

        continuous = False
        ptt_held = False
        wakeword_enabled = config.stt.wakeword_enabled

        # Reset wake state on start
        if wakeword_enabled:
            from claudible.stt.keybind import _write_wake_state
            _write_wake_state("sleeping")

        def on_press(key: Any) -> None:
            nonlocal continuous, ptt_held

            if key == toggle_key:
                continuous = not continuous
                if continuous:
                    log.info("Continuous STT ON (toggle key)")
                    dictation.start()
                    continuous_on()
                else:
                    log.info("Continuous STT OFF (toggle key)")
                    dictation.stop()
                    continuous_off()

            elif key == ptt_key and not continuous and not ptt_held:
                ptt_held = True
                log.info("PTT key down")
                if wakeword_enabled:
                    from claudible.stt.keybind import _write_wake_state
                    _write_wake_state("awake")
                dictation.start()
                if ptt_on:
                    ptt_on()

        def on_release(key: Any) -> None:
            nonlocal ptt_held

            if key == ptt_key and ptt_held:
                ptt_held = False
                log.info("PTT key up")
                dictation.stop()
                if wakeword_enabled:
                    from claudible.stt.keybind import _write_wake_state
                    _write_wake_state("sleeping")
                if ptt_off:
                    ptt_off()

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

        try:
            while not stop_event.is_set():
                stop_event.wait(0.5)
                # Poll wake word state for tray updates
                if wakeword_enabled and continuous and wake_state_changed:
                    from claudible.stt.keybind import _read_wake_state
                    current = _read_wake_state()
                    wake_state_changed(current)
        finally:
            listener.stop()
            if dictation.is_running:
                dictation.stop()
            log.info("Key listener stopped")
