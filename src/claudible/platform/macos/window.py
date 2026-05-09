"""macOS window backend — AppleScript via osascript."""

from __future__ import annotations

import logging
import subprocess

from claudible.platform.base import WindowBackend
from claudible.stt.windows import (
    clear_all_windows,
    read_window_state,
    write_window_state,
)

log = logging.getLogger(__name__)


def _osascript(script: str) -> str:
    """Run AppleScript and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()}")
    return result.stdout.strip()


class AppleScriptWindow(WindowBackend):
    """AppleScript-based window management for macOS."""

    def capture_active_window(self) -> tuple[int, str]:
        # macOS doesn't have integer window IDs like X11.
        # We use the frontmost app's bundle ID hash as a pseudo-ID
        # and the window title for display.
        try:
            app_name = _osascript(
                'tell application "System Events" to get name of first application process '
                "whose frontmost is true"
            )
            title = _osascript(
                'tell application "System Events" to get title of front window of '
                "first application process whose frontmost is true"
            )
            # Create a stable pseudo-ID from app name + title
            pseudo_id = hash(f"{app_name}:{title}") & 0x7FFFFFFF
            return pseudo_id, f"{app_name} - {title}"
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"Failed to capture active window: {e}")

    def register_window(self, slot: str, window_id: int | None = None) -> dict:
        if window_id is None:
            wid, title = self.capture_active_window()
        else:
            wid = window_id
            title = "(registered)"

        state = read_window_state()
        state.setdefault("windows", {})[slot] = {
            "window_id": wid,
            "title": title,
        }
        write_window_state(state)
        log.info("Registered window slot %s: %d (%s)", slot, wid, title)
        return state

    def validate_window(self, window_id: int) -> bool:
        # macOS pseudo-IDs aren't validatable the same way.
        # Return True if the window state entry exists.
        state = read_window_state()
        for entry in state.get("windows", {}).values():
            if entry.get("window_id") == window_id:
                return True
        return False

    def read_window_state(self) -> dict:
        return read_window_state()

    def clear_all_windows(self) -> None:
        clear_all_windows()
