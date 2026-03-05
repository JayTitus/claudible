"""Window slot management for locked dictation.

Manages window registrations stored in ~/.cache/claudible/windows.json.
Uses xdotool for X11 window capture and validation.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from claudible.paths import WINDOW_STATE

log = logging.getLogger(__name__)


def read_window_state() -> dict:
    """Read the window state file. Returns dict with windows and default_slot."""
    try:
        with open(WINDOW_STATE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"windows": {}, "default_slot": "1"}


def write_window_state(state: dict) -> None:
    """Write window state atomically via tmp+rename."""
    tmp_path = str(WINDOW_STATE) + ".tmp"
    try:
        os.makedirs(str(WINDOW_STATE.parent), exist_ok=True)
        with open(tmp_path, "w") as f:
            json.dump(state, f)
        os.rename(tmp_path, str(WINDOW_STATE))
    except OSError:
        log.debug("Failed to write window state", exc_info=True)


def capture_active_window() -> tuple[int, str]:
    """Capture the currently focused X11 window.

    Returns (window_id, window_title).
    Raises RuntimeError if xdotool is not available or fails.
    """
    try:
        wid_raw = subprocess.check_output(
            ["xdotool", "getactivewindow"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
        wid = int(wid_raw)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"Failed to capture active window (xdotool): {e}")
    except ValueError:
        raise RuntimeError(f"xdotool returned non-integer window ID: {wid_raw!r}")

    try:
        title = subprocess.check_output(
            ["xdotool", "getwindowname", str(wid)],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        title = "(unknown)"

    return wid, title


def register_window(slot: str, window_id: int | None = None) -> dict:
    """Register a window to a slot. Captures active window if no ID given.

    Returns the updated state dict.
    """
    if window_id is None:
        wid, title = capture_active_window()
    else:
        wid = window_id
        try:
            title = subprocess.check_output(
                ["xdotool", "getwindowname", str(wid)],
                stderr=subprocess.DEVNULL,
                timeout=3,
            ).decode().strip()
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            title = "(unknown)"

    state = read_window_state()
    state.setdefault("windows", {})[slot] = {
        "window_id": wid,
        "title": title,
    }
    write_window_state(state)
    log.info("Registered window slot %s: %d (%s)", slot, wid, title)
    return state


def unregister_window(slot: str) -> dict:
    """Remove a window slot. Returns updated state."""
    state = read_window_state()
    windows = state.get("windows", {})
    if slot in windows:
        del windows[slot]
        write_window_state(state)
        log.info("Unregistered window slot %s", slot)
    return state


def validate_window(window_id: int) -> bool:
    """Check if an X11 window still exists."""
    try:
        subprocess.check_output(
            ["xdotool", "getwindowname", str(window_id)],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def clear_all_windows() -> None:
    """Delete the windows.json state file."""
    try:
        Path(WINDOW_STATE).unlink(missing_ok=True)
        log.info("Cleared all window registrations")
    except OSError:
        log.debug("Failed to clear window state", exc_info=True)
