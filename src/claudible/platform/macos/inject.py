"""macOS keystroke / text injection via osascript / System Events.

Implements the :class:`~claudible.stt.router.Injector` protocol for
macOS. Window lock isn't supported here — text always goes to the
frontmost application.
"""

from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

_KEY_TO_APPLESCRIPT = {
    "Return": "key code 36",
    "Tab": "key code 48",
    "BackSpace": "key code 51",
    "Escape": "key code 53",
}


class OsaScriptInjector:
    """macOS injector using AppleScript / System Events."""

    def __init__(self) -> None:
        self._target: dict = {}

    def set_target(self, target: dict) -> None:
        self._target = target or {}

    def send_text(self, text: str) -> bool:
        if not text:
            return True
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to keystroke "{escaped}"'],
                capture_output=True, timeout=3,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def send_key(self, key: str) -> bool:
        cmd = _KEY_TO_APPLESCRIPT.get(key)
        if cmd is None:
            return False
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to {cmd}'],
                capture_output=True, timeout=3,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_active_window(self) -> tuple[int | None, str]:
        try:
            out = subprocess.check_output(
                ["osascript", "-e",
                 'tell application "System Events" to get name of '
                 'first application process whose frontmost is true'],
                stderr=subprocess.DEVNULL, timeout=3,
            ).decode().strip()
            return None, out
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            return None, ""

    def resolve_target(self, slot: str) -> dict:
        # macOS doesn't support window-lock by id; always frontmost
        return {}
