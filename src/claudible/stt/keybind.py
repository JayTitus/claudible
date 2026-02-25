"""Push-to-talk keybinding listener using evdev."""

from __future__ import annotations

import logging
import select
from pathlib import Path

import evdev
from evdev import InputDevice, categorize, ecodes

from claudible.config import Config
from claudible.stt.dictation import Dictation

log = logging.getLogger(__name__)


def find_keyboards() -> list[InputDevice]:
    """Find all keyboard input devices."""
    devices = []
    for path in sorted(Path("/dev/input/").glob("event*")):
        try:
            dev = InputDevice(str(path))
            caps = dev.capabilities(verbose=True)
            # Check if device has EV_KEY with actual key events
            for cap_type, events in caps.items():
                if cap_type[0] == "EV_KEY":
                    # Has keyboard-like keys
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
                        # Toggle mode
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
