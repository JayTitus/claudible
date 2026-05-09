"""Linux window backend — delegates to stt/windows.py (xdotool)."""

from __future__ import annotations

from claudible.platform.base import WindowBackend


class XdotoolWindow(WindowBackend):
    """xdotool-based window management for X11."""

    def capture_active_window(self) -> tuple[int, str]:
        from claudible.stt.windows import capture_active_window

        return capture_active_window()

    def register_window(self, slot: str, window_id: int | None = None) -> dict:
        from claudible.stt.windows import register_window

        return register_window(slot, window_id)

    def validate_window(self, window_id: int) -> bool:
        from claudible.stt.windows import validate_window

        return validate_window(window_id)

    def read_window_state(self) -> dict:
        from claudible.stt.windows import read_window_state

        return read_window_state()

    def clear_all_windows(self) -> None:
        from claudible.stt.windows import clear_all_windows

        clear_all_windows()
