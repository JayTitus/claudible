"""System tray application for claudible."""

from __future__ import annotations

import logging
import os
import threading

# Ensure GI_TYPELIB_PATH includes system typelibs (needed in venvs)
_SYSTEM_TYPELIB = "/usr/lib/x86_64-linux-gnu/girepository-1.0"
if os.path.isdir(_SYSTEM_TYPELIB):
    existing = os.environ.get("GI_TYPELIB_PATH", "")
    if _SYSTEM_TYPELIB not in existing:
        parts = f"{_SYSTEM_TYPELIB}:{existing}" if existing else _SYSTEM_TYPELIB
        os.environ["GI_TYPELIB_PATH"] = parts

import pystray  # noqa: E402 — must be after GI_TYPELIB_PATH setup

from claudible.config import Config  # noqa: E402
from claudible.gui.icons import icon_active, icon_error, icon_inactive  # noqa: E402
from claudible.paths import CACHE_DIR, TTS_MUTE_FLAG  # noqa: E402
from claudible.stt.dictation import Dictation  # noqa: E402

log = logging.getLogger(__name__)


class TrayApp:
    """pystray-based system tray icon with STT/TTS toggles."""

    def __init__(self) -> None:
        self.cfg = Config.load()
        self._stt_continuous = False  # Scroll Lock continuous mode
        self._tts_enabled = not TTS_MUTE_FLAG.exists()
        self._server_healthy = False
        self._key_stop_event = threading.Event()
        self._key_thread: threading.Thread | None = None
        self._health_stop = threading.Event()
        self._dictation = Dictation(self.cfg)

        self.icon = pystray.Icon(
            "claudible",
            icon=icon_inactive(),
            title="Claudible",
            menu=pystray.Menu(
                pystray.MenuItem(
                    lambda _: f"Server: {'running' if self._server_healthy else 'stopped'}",
                    None,
                    enabled=False,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    lambda _: f"STT: {'ON' if self._stt_continuous else 'OFF'}",
                    self._toggle_stt_from_menu,
                ),
                pystray.MenuItem(
                    lambda _: f"Notifications: {'ON' if self._tts_enabled else 'OFF'}",
                    self._toggle_tts,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open Settings...", self._open_settings),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def run(self) -> None:
        """Start the tray icon (blocks)."""
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()

        # Start unified key listener (handles both PTT and toggle)
        self._key_stop_event.clear()
        self._key_thread = threading.Thread(target=self._run_key_listener, daemon=True)
        self._key_thread.start()

        self.icon.run()

    def _run_key_listener(self) -> None:
        try:
            from claudible.stt.keybind import run_key_listener

            run_key_listener(
                config=self.cfg,
                dictation=self._dictation,
                continuous_on=self._on_continuous_on,
                continuous_off=self._on_continuous_off,
                ptt_on=self._on_ptt_on,
                ptt_off=self._on_ptt_off,
                stop_event=self._key_stop_event,
            )
        except Exception:
            log.exception("Key listener thread error")

    def _on_continuous_on(self) -> None:
        """Called by key listener when continuous mode turns ON."""
        self._stt_continuous = True
        self.icon.icon = icon_active()
        self.icon.update_menu()
        log.info("STT continuous ON")

    def _on_continuous_off(self) -> None:
        """Called by key listener when continuous mode turns OFF."""
        self._stt_continuous = False
        self.icon.icon = icon_inactive()
        self.icon.update_menu()
        log.info("STT continuous OFF")

    def _on_ptt_on(self) -> None:
        """Called by key listener when PTT key is held down."""
        self.icon.icon = icon_active()
        self.icon.update_menu()

    def _on_ptt_off(self) -> None:
        """Called by key listener when PTT key is released."""
        if not self._stt_continuous:
            self.icon.icon = icon_inactive()
            self.icon.update_menu()

    def _update_icon(self) -> None:
        if self._stt_continuous:
            self.icon.icon = icon_active()
        else:
            self.icon.icon = icon_inactive()
        self.icon.update_menu()

    def _toggle_stt_from_menu(self) -> None:
        """Toggle continuous STT from the tray menu click."""
        if self._stt_continuous:
            self._dictation.stop()
            self._on_continuous_off()
        else:
            self._dictation.start()
            self._on_continuous_on()

    def _toggle_tts(self) -> None:
        self._tts_enabled = not self._tts_enabled
        if self._tts_enabled:
            TTS_MUTE_FLAG.unlink(missing_ok=True)
            log.info("TTS unmuted")
        else:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            TTS_MUTE_FLAG.touch()
            log.info("TTS muted")
        self._update_icon()

    def _open_settings(self) -> None:
        def _run_settings() -> None:
            try:
                import subprocess
                import sys

                subprocess.Popen(
                    [sys.executable, "-m", "claudible.cli", "tui"],
                    start_new_session=True,
                )
            except Exception:
                log.exception("Failed to launch TUI settings")
            # Reload config in case user changed settings
            self.cfg = Config.load()

        threading.Thread(target=_run_settings, daemon=True).start()

    def _health_loop(self) -> None:
        import asyncio

        from claudible.tts.client import TTSClient

        client = TTSClient(base_url=f"http://{self.cfg.tts.host}:{self.cfg.tts.port}")
        while not self._health_stop.is_set():
            try:
                healthy = asyncio.run(client.health())
            except Exception:
                healthy = False
            if healthy != self._server_healthy:
                self._server_healthy = healthy
                self.icon.update_menu()
            self._health_stop.wait(5)

    def _quit(self) -> None:
        self._health_stop.set()
        self._key_stop_event.set()
        if self._key_thread:
            self._key_thread.join(timeout=3)
        if self._dictation.is_running:
            self._dictation.stop()
        self.icon.stop()
