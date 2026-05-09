"""Platform detection and backend dispatch.

Usage::

    from claudible.platform import get_keyboard_backend, get_window_backend

    kb = get_keyboard_backend()
    if kb is None:
        print("Keyboard input not available on this platform")
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claudible.platform.base import (
        DaemonBackend,
        KeyboardBackend,
        NoiseBackend,
        ProcessBackend,
        SetupBackend,
        STTBackend,
        WindowBackend,
    )

LINUX = "linux"
MACOS = "darwin"
WINDOWS = "win32"


def detect_platform() -> str:
    """Return the current platform identifier."""
    if sys.platform.startswith("linux"):
        return LINUX
    elif sys.platform == "darwin":
        return MACOS
    elif sys.platform == "win32":
        return WINDOWS
    return sys.platform


def get_keyboard_backend() -> KeyboardBackend | None:
    """Return the keyboard backend for the current platform, or None."""
    plat = detect_platform()
    if plat == LINUX:
        try:
            from claudible.platform.linux.keyboard import EvdevKeyboard

            return EvdevKeyboard()
        except ImportError:
            return None
    elif plat == MACOS:
        try:
            from claudible.platform.macos.keyboard import PynputKeyboard

            return PynputKeyboard()
        except ImportError:
            return None
    return None


def get_window_backend() -> WindowBackend | None:
    """Return the window backend for the current platform, or None."""
    plat = detect_platform()
    if plat == LINUX:
        try:
            from claudible.platform.linux.window import XdotoolWindow

            return XdotoolWindow()
        except ImportError:
            return None
    elif plat == MACOS:
        try:
            from claudible.platform.macos.window import AppleScriptWindow

            return AppleScriptWindow()
        except ImportError:
            return None
    return None


def get_process_backend() -> ProcessBackend | None:
    """Return the process backend for the current platform, or None."""
    plat = detect_platform()
    if plat == LINUX:
        try:
            from claudible.platform.linux.process import ProcfsProcess

            return ProcfsProcess()
        except ImportError:
            return None
    elif plat == MACOS:
        try:
            from claudible.platform.macos.process import PsutilProcess

            return PsutilProcess()
        except ImportError:
            return None
    return None


def get_stt_backend() -> STTBackend | None:
    """Return the STT backend for the current platform, or None."""
    plat = detect_platform()
    if plat == LINUX:
        try:
            from claudible.platform.linux.stt import NerdDictationSTT

            return NerdDictationSTT()
        except ImportError:
            return None
    elif plat == MACOS:
        try:
            from claudible.platform.macos.stt import DirectVoskSTT

            return DirectVoskSTT()
        except ImportError:
            return None
    return None


def get_noise_backend() -> NoiseBackend | None:
    """Return the noise suppression backend for the current platform, or None."""
    plat = detect_platform()
    if plat == LINUX:
        try:
            from claudible.platform.linux.noise import PipeWireNoise

            return PipeWireNoise()
        except ImportError:
            return None
    # macOS: no noise suppression backend (system-level Voice Isolation)
    return None


def get_daemon_backend() -> DaemonBackend | None:
    """Return the daemon/service backend for the current platform, or None."""
    plat = detect_platform()
    if plat == LINUX:
        try:
            from claudible.platform.linux.daemon import SystemdDaemon

            return SystemdDaemon()
        except ImportError:
            return None
    elif plat == MACOS:
        try:
            from claudible.platform.macos.daemon import LaunchdDaemon

            return LaunchdDaemon()
        except ImportError:
            return None
    return None


def get_setup_backend() -> SetupBackend | None:
    """Return the setup backend for the current platform, or None."""
    plat = detect_platform()
    if plat == LINUX:
        try:
            from claudible.platform.linux.setup import AptSetup

            return AptSetup()
        except ImportError:
            return None
    elif plat == MACOS:
        try:
            from claudible.platform.macos.setup import BrewSetup

            return BrewSetup()
        except ImportError:
            return None
    return None


def available_backends() -> dict[str, bool]:
    """Return which backends are available on this platform.

    Useful for the web UI capabilities endpoint.
    """
    return {
        "keyboard": get_keyboard_backend() is not None,
        "window": get_window_backend() is not None,
        "process": get_process_backend() is not None,
        "stt": get_stt_backend() is not None,
        "noise": get_noise_backend() is not None,
        "daemon": get_daemon_backend() is not None,
        "setup": get_setup_backend() is not None,
        "platform": detect_platform(),
    }
