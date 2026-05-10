"""Linux keystroke / text injection — Konsole D-Bus + xdotool.

Implements the :class:`~claudible.stt.router.Injector` protocol for X11.
Konsole sessions resolved via D-Bus get text via ``Session.sendText``,
which sidesteps focus and X11 input quirks. Anything else falls back
to xdotool typing into a specific window id (when window-locked) or
the focused window (when not).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess

from claudible.paths import WINDOW_STATE

log = logging.getLogger(__name__)

_KEY_TO_CHAR = {
    "Return": "\n",
    "Tab": "\t",
    "BackSpace": "\x7f",
    "Escape": "\x1b",
}


class XdotoolInjector:
    """Linux/X11 injector with Konsole D-Bus fast path."""

    def __init__(self) -> None:
        self._target: dict = {}

    # ── Router contract ─────────────────────────────────────────────────

    def set_target(self, target: dict) -> None:
        self._target = target or {}

    def send_text(self, text: str) -> bool:
        if not text:
            return True

        svc = self._target.get("konsole_service")
        sess = self._target.get("konsole_session")
        if svc and sess and self._konsole_send_text(svc, sess, text):
            return True

        wid = self._target.get("window_id")
        if wid:
            if self._window_exists(wid):
                return self._xdotool_type_to_window(wid, text)
            self._remove_dead_window(wid)
            # Fall through to focused-window typing

        return self._xdotool_type_focused(text)

    def send_key(self, key: str) -> bool:
        svc = self._target.get("konsole_service")
        sess = self._target.get("konsole_session")
        if svc and sess and self._konsole_send_key(svc, sess, key):
            return True

        wid = self._target.get("window_id")
        if wid and self._window_exists(wid):
            return self._xdotool_key_to_window(wid, key)

        return self._xdotool_key_focused(key)

    def get_active_window(self) -> tuple[int | None, str]:
        try:
            wid_out = subprocess.check_output(
                ["xdotool", "getactivewindow"],
                stderr=subprocess.DEVNULL, timeout=2,
            ).decode().strip()
            wid = int(wid_out)
            title = subprocess.check_output(
                ["xdotool", "getwindowname", str(wid)],
                stderr=subprocess.DEVNULL, timeout=2,
            ).decode().strip()
            return wid, title
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired, ValueError):
            return None, ""

    def resolve_target(self, slot: str) -> dict:
        state = self._read_window_state()
        windows = state.get("windows", {})
        entry = windows.get(slot)
        if not entry:
            return {}

        result = {
            "window_id": entry.get("window_id"),
            "konsole_service": entry.get("konsole_service"),
            "konsole_session": entry.get("konsole_session"),
        }

        wid = result.get("window_id")
        if wid and not self._window_exists(wid):
            del windows[slot]
            self._write_window_state(state)
            return {}
        return result

    # ── Konsole D-Bus ───────────────────────────────────────────────────

    @staticmethod
    def _konsole_send_text(service: str, session: str, text: str) -> bool:
        try:
            subprocess.Popen(
                ["qdbus", service, session,
                 "org.kde.konsole.Session.sendText", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except (FileNotFoundError, OSError):
            return False

    @classmethod
    def _konsole_send_key(cls, service: str, session: str, key: str) -> bool:
        char = _KEY_TO_CHAR.get(key)
        if char is None:
            return False
        return cls._konsole_send_text(service, session, char)

    # ── xdotool ─────────────────────────────────────────────────────────

    @staticmethod
    def _xdotool_type_focused(text: str) -> bool:
        try:
            subprocess.Popen(
                ["xdotool", "type", "--clearmodifiers", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def _xdotool_type_to_window(wid: int, text: str) -> bool:
        try:
            subprocess.Popen(
                ["xdotool", "type", "--clearmodifiers", "--window", str(wid), text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def _xdotool_key_focused(key: str) -> bool:
        try:
            subprocess.Popen(
                ["xdotool", "key", key],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def _xdotool_key_to_window(wid: int, key: str) -> bool:
        try:
            subprocess.Popen(
                ["xdotool", "key", "--window", str(wid), key],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def _window_exists(wid: int) -> bool:
        try:
            subprocess.check_output(
                ["xdotool", "getwindowname", str(wid)],
                stderr=subprocess.DEVNULL, timeout=2,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            return False

    # ── Window state helpers ────────────────────────────────────────────

    @staticmethod
    def _read_window_state() -> dict:
        try:
            with open(WINDOW_STATE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"windows": {}, "default_slot": "1"}

    @classmethod
    def _write_window_state(cls, state: dict) -> None:
        tmp = str(WINDOW_STATE) + ".tmp"
        try:
            os.makedirs(str(WINDOW_STATE.parent), exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(state, f)
            os.rename(tmp, str(WINDOW_STATE))
        except OSError:
            pass

    @classmethod
    def _remove_dead_window(cls, wid: int) -> None:
        state = cls._read_window_state()
        windows = state.get("windows", {})
        to_remove = [s for s, w in windows.items() if w.get("window_id") == wid]
        for s in to_remove:
            del windows[s]
        if to_remove:
            cls._write_window_state(state)
