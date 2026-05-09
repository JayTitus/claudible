"""Abstract base classes for platform-specific backends."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class KeyboardBackend(ABC):
    """Global keyboard listener for PTT and toggle keys."""

    @abstractmethod
    def run_ptt(self, config: Any) -> None:
        """Run standalone push-to-talk listener (blocks)."""

    @abstractmethod
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
        """Unified key listener for PTT + toggle (blocks)."""


class WindowBackend(ABC):
    """Window capture and management."""

    @abstractmethod
    def capture_active_window(self) -> tuple[int, str]:
        """Get the focused window. Returns (window_id, title)."""

    @abstractmethod
    def register_window(self, slot: str, window_id: int | None = None) -> dict:
        """Register a window to a slot. Returns updated state."""

    @abstractmethod
    def validate_window(self, window_id: int) -> bool:
        """Check if a window still exists."""

    @abstractmethod
    def read_window_state(self) -> dict:
        """Read the window state file."""

    @abstractmethod
    def clear_all_windows(self) -> None:
        """Clear all window registrations."""


class ProcessBackend(ABC):
    """Process watching for auto window lock."""

    @abstractmethod
    def create_watcher(
        self, config: Any, on_slots_changed: Callable[[int], None] | None = None,
    ) -> Any:
        """Create a process watcher instance. Returns object with start()/stop()."""

    @abstractmethod
    def scan_for_names(self, names: list[str]) -> list[dict]:
        """Scan for processes matching names. Returns list of {pid, name, cmdline}."""

    @abstractmethod
    def find_terminal_window(self, pid: int) -> int | None:
        """Find the terminal window for a process."""


class STTBackend(ABC):
    """Speech-to-text engine."""

    @abstractmethod
    def create_dictation(self, config: Any) -> Any:
        """Create a Dictation-compatible instance. Returns object with start()/stop()/is_available/is_running."""


class NoiseBackend(ABC):
    """Noise suppression configuration."""

    @abstractmethod
    def is_available(self) -> bool:
        """Whether noise suppression is available on this platform."""

    @abstractmethod
    def is_active(self) -> bool:
        """Whether noise suppression is currently active."""

    @abstractmethod
    def enable(self, **kwargs: Any) -> bool:
        """Enable noise suppression."""

    @abstractmethod
    def disable(self) -> bool:
        """Disable noise suppression."""


class DaemonBackend(ABC):
    """Background service management."""

    @abstractmethod
    def is_service_available(self) -> bool:
        """Check if a system service manager is available (systemd, launchd)."""

    @abstractmethod
    def is_service_enabled(self) -> bool:
        """Check if the claudible service is enabled."""

    @abstractmethod
    def start_service(self) -> bool:
        """Start the claudible service via OS service manager."""

    @abstractmethod
    def stop_service(self) -> bool:
        """Stop the claudible service via OS service manager."""


class SetupBackend(ABC):
    """Platform-specific setup checks."""

    @abstractmethod
    def check_system_deps(self) -> bool:
        """Check/install system dependencies."""

    @abstractmethod
    def check_input_permissions(self, auto_yes: bool = False) -> bool:
        """Check permissions for keyboard input capture."""

    @abstractmethod
    def get_system_info(self) -> dict:
        """Return platform-specific system info (RAM, GPU, etc.)."""
