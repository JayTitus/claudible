"""Keybinding listeners for STT using evdev (Linux only)."""

from __future__ import annotations

import logging
import select
import threading
from collections.abc import Callable
from pathlib import Path

try:
    from evdev import InputDevice, categorize, ecodes
except ImportError:
    raise ImportError(
        "evdev is required for keyboard input on Linux. "
        "Install with: pip install claudible[linux]"
    )

from claudible.config import Config
from claudible.paths import WAKEWORD_STATE
from claudible.stt.dictation import Dictation

log = logging.getLogger(__name__)


def _write_wake_state(state: str, activated_at: float = 0.0) -> None:
    """Write wake word state file atomically."""
    import json
    import os
    import time

    data = {"state": state, "activated_at": activated_at or (time.time() if state == "awake" else 0.0)}
    tmp_path = str(WAKEWORD_STATE) + ".tmp"
    try:
        os.makedirs(str(WAKEWORD_STATE.parent), exist_ok=True)
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.rename(tmp_path, str(WAKEWORD_STATE))
    except OSError:
        log.debug("Failed to write wake state", exc_info=True)


def _read_wake_state() -> str:
    """Read current wake word state. Returns 'sleeping' or 'awake'."""
    import json

    try:
        with open(WAKEWORD_STATE, "r") as f:
            return json.load(f).get("state", "sleeping")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "sleeping"


def find_keyboards() -> list[InputDevice]:
    """Find all keyboard input devices."""
    devices = []
    for path in sorted(Path("/dev/input/").glob("event*")):
        try:
            dev = InputDevice(str(path))
            caps = dev.capabilities(verbose=True)
            for cap_type, events in caps.items():
                if cap_type[0] == "EV_KEY":
                    key_names = [e[0] for e in events]
                    if any("KEY_" in str(k) for k in key_names):
                        devices.append(dev)
                        break
        except (PermissionError, OSError):
            continue
    return devices


def run_ptt(config: Config | None = None) -> None:
    """Run the push-to-talk listener. Blocks until interrupted."""
    cfg = config or Config.load()
    key_name = cfg.stt.push_to_talk_key
    hold_mode = cfg.stt.hold_mode

    key_code = getattr(ecodes, key_name, None)
    if key_code is None:
        raise ValueError(f"Unknown key: {key_name}. Use evdev key names like KEY_SCROLLLOCK.")

    dictation = Dictation(cfg)
    if not dictation.is_available:
        raise RuntimeError("nerd-dictation not found. Cannot start PTT listener.")

    keyboards = find_keyboards()
    if not keyboards:
        raise RuntimeError(
            "No keyboard devices found. Ensure you have read access to /dev/input/event*. "
            "You may need to add your user to the 'input' group."
        )

    log.info(
        "PTT listener started — %s %s on %d device(s)",
        "hold" if hold_mode else "toggle",
        key_name,
        len(keyboards),
    )

    try:
        while True:
            r, _, _ = select.select(keyboards, [], [])
            for dev in r:
                for event in dev.read():
                    if event.type != ecodes.EV_KEY:
                        continue
                    key_event = categorize(event)
                    if key_event.scancode != key_code:
                        continue

                    if hold_mode:
                        if key_event.keystate == key_event.key_down:
                            log.debug("PTT key down — starting dictation")
                            dictation.start()
                        elif key_event.keystate == key_event.key_up:
                            log.debug("PTT key up — stopping dictation")
                            dictation.stop()
                    else:
                        if key_event.keystate == key_event.key_down:
                            if dictation.is_running:
                                log.debug("PTT toggle — stopping dictation")
                                dictation.stop()
                            else:
                                log.debug("PTT toggle — starting dictation")
                                dictation.start()
    except KeyboardInterrupt:
        dictation.stop()
        log.info("PTT listener stopped")


def run_key_listener(
    config: Config,
    dictation: Dictation,
    continuous_on: Callable[[], None],
    continuous_off: Callable[[], None],
    stop_event: threading.Event,
    ptt_on: Callable[[], None] | None = None,
    ptt_off: Callable[[], None] | None = None,
    wake_state_changed: Callable[[str], None] | None = None,
    is_continuous: Callable[[], bool] | None = None,
) -> None:
    """Unified key listener for both PTT (hold) and continuous toggle.

    - Toggle key (Scroll Lock): starts/stops continuous dictation
    - PTT key (Right Ctrl): hold-to-speak (only when continuous is off)

    Args:
        config: Claudible config.
        dictation: Shared Dictation instance.
        continuous_on: Called when continuous mode turns ON.
        continuous_off: Called when continuous mode turns OFF.
        stop_event: Set to stop the listener.
        ptt_on: Called when PTT key is pressed.
        ptt_off: Called when PTT key is released.
        wake_state_changed: Called when wake word state changes (receives 'awake' or 'sleeping').
        is_continuous: Callable that returns whether continuous mode is active
            (accounts for external sources like process watcher).
    """
    ptt_key_name = config.stt.push_to_talk_key
    toggle_key_name = config.stt.toggle_key

    ptt_code = getattr(ecodes, ptt_key_name, None)
    toggle_code = getattr(ecodes, toggle_key_name, None)

    if ptt_code is None:
        log.warning("Unknown PTT key: %s", ptt_key_name)
    if toggle_code is None:
        log.warning("Unknown toggle key: %s", toggle_key_name)
    if ptt_code is None and toggle_code is None:
        return

    if not dictation.is_available:
        log.error("nerd-dictation not found — key listener not started")
        return

    keyboards = find_keyboards()
    if not keyboards:
        log.warning("No keyboard devices found — key listener not started")
        return

    log.info(
        "Key listener started — PTT=%s, Toggle=%s on %d device(s)",
        ptt_key_name,
        toggle_key_name,
        len(keyboards),
    )

    continuous = False
    ptt_held = False
    wakeword_enabled = config.stt.wakeword_enabled
    _last_wake_state = "sleeping"

    # Reset wake state file on start
    if wakeword_enabled:
        _write_wake_state("sleeping")

    try:
        while not stop_event.is_set():
            try:
                r, _, _ = select.select(keyboards, [], [], 0.5)
            except (OSError, ValueError):
                # A device disconnected — refresh device list
                keyboards = find_keyboards()
                if not keyboards:
                    log.warning("All keyboard devices lost — waiting for reconnect")
                    stop_event.wait(2)
                    keyboards = find_keyboards()
                    if not keyboards:
                        continue
                log.info("Refreshed keyboard devices: %d found", len(keyboards))
                continue

            # Poll wake word state for tray icon updates (runs every select timeout)
            if wakeword_enabled and continuous and wake_state_changed:
                current_state = _read_wake_state()
                if current_state != _last_wake_state:
                    _last_wake_state = current_state
                    wake_state_changed(current_state)

            for dev in r:
                try:
                    events = list(dev.read())
                except OSError:
                    # Device disconnected mid-read — remove it, refresh next loop
                    log.warning("Device %s disconnected", dev.path)
                    keyboards = [d for d in keyboards if d is not dev]
                    if not keyboards:
                        keyboards = find_keyboards()
                        log.info("Refreshed keyboard devices: %d found", len(keyboards))
                    continue

                for event in events:
                    if event.type != ecodes.EV_KEY:
                        continue
                    key_event = categorize(event)
                    code = key_event.scancode
                    state = key_event.keystate

                    # --- Toggle key: continuous dictation ---
                    if code == toggle_code and state == key_event.key_down:
                        continuous = not continuous
                        if continuous:
                            log.info("Continuous STT ON (toggle key)")
                            dictation.start()
                            continuous_on()
                        else:
                            log.info("Continuous STT OFF (toggle key)")
                            dictation.stop()
                            continuous_off()

                    # --- PTT key: hold-to-speak ---
                    if code == ptt_code and not continuous:
                        if state == key_event.key_down and not ptt_held:
                            ptt_held = True
                            log.info("PTT key down — starting dictation")
                            if wakeword_enabled:
                                _write_wake_state("awake")
                            dictation.start()
                            if ptt_on:
                                ptt_on()
                        elif state == key_event.key_up and ptt_held:
                            ptt_held = False
                            log.info("PTT key up — stopping dictation")
                            dictation.stop()
                            if wakeword_enabled:
                                _write_wake_state("sleeping")
                            if ptt_off:
                                ptt_off()
    except Exception:
        log.exception("Key listener error")
    finally:
        if dictation.is_running:
            dictation.stop()
        log.info("Key listener stopped")
