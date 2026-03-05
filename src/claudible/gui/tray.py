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
from claudible.gui.icons import icon_active, icon_error, icon_inactive, icon_listening  # noqa: E402
from claudible.paths import CACHE_DIR, TTS_MUTE_FLAG, WAKEWORD_STATE  # noqa: E402
from claudible.stt.dictation import Dictation  # noqa: E402

log = logging.getLogger(__name__)


class TrayApp:
    """pystray-based system tray icon with STT/TTS toggles."""

    def __init__(self) -> None:
        self.cfg = Config.load()
        self._stt_continuous = False  # Scroll Lock continuous mode
        self._tts_enabled = not TTS_MUTE_FLAG.exists()
        self._server_healthy = False
        self._wakeword_state = "sleeping"
        self._key_stop_event = threading.Event()
        self._key_thread: threading.Thread | None = None
        self._health_stop = threading.Event()
        self._dictation = Dictation(self.cfg)
        self._proc_watcher = None

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
                    lambda _: self._stt_menu_text(),
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

    def _stt_menu_text(self) -> str:
        """Generate STT menu text based on current state."""
        if not self._stt_continuous:
            return "STT: OFF"
        if self.cfg.stt.wakeword_enabled:
            if self._wakeword_state == "awake":
                return "STT: Active"
            # Find the first trigger word for display
            triggers = list(self.cfg.rephrase.trigger_words.values())
            if triggers:
                return f"STT: Listening for '{triggers[0]}'..."
            return "STT: Listening..."
        return "STT: ON"

    def run(self) -> None:
        """Start the tray icon (blocks)."""
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()

        # Start unified key listener (handles both PTT and toggle)
        self._key_stop_event.clear()
        self._key_thread = threading.Thread(target=self._run_key_listener, daemon=True)
        self._key_thread.start()

        # Start process watcher for auto window lock
        self._start_proc_watcher()

        # Register STT restart callback so the web UI can trigger it
        try:
            from claudible.web.router import register_stt_restart

            register_stt_restart(self._restart_key_listener)
        except Exception:
            pass

        self.icon.run()

    def _start_proc_watcher(self) -> None:
        """Start the process watcher if window lock is enabled and processes are configured."""
        if self.cfg.stt.window_lock_enabled and self.cfg.stt.watched_processes:
            try:
                from claudible.stt.procwatch import ProcessWatcher

                self._proc_watcher = ProcessWatcher(self.cfg, on_slots_changed=self._on_slots_changed)
                self._proc_watcher.start()
            except Exception:
                log.exception("Failed to start process watcher")

    def _stop_proc_watcher(self) -> None:
        """Stop the process watcher if running."""
        if self._proc_watcher:
            self._proc_watcher.stop()
            self._proc_watcher = None

    def _on_slots_changed(self, slot_count: int) -> None:
        """Auto-toggle continuous STT when watched processes appear/disappear."""
        if slot_count > 0 and not self._stt_continuous:
            log.info("Watched process detected — auto-starting STT")
            self._dictation.start()
            self._on_continuous_on()
        elif slot_count == 0 and self._stt_continuous:
            log.info("No watched processes — auto-stopping STT")
            self._dictation.stop()
            self._on_continuous_off()

    def _restart_key_listener(self) -> None:
        """Stop and restart the key listener with fresh config."""
        log.info("Restarting STT key listener with new config...")
        # Stop existing listener
        self._key_stop_event.set()
        if self._key_thread and self._key_thread.is_alive():
            self._key_thread.join(timeout=3)
        # Stop any running dictation
        if self._dictation.is_running:
            self._dictation.stop()
        self._on_continuous_off()
        # Stop process watcher
        self._stop_proc_watcher()
        # Reload config
        self.cfg = Config.load()
        self._dictation = Dictation(self.cfg)
        # Restart key listener
        self._key_stop_event = threading.Event()
        self._key_thread = threading.Thread(target=self._run_key_listener, daemon=True)
        self._key_thread.start()
        # Restart process watcher with new config
        self._start_proc_watcher()
        log.info("STT key listener restarted")

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
                wake_state_changed=self._on_wake_state_changed,
            )
        except Exception:
            log.exception("Key listener thread error")

    def _on_continuous_on(self) -> None:
        """Called by key listener when continuous mode turns ON."""
        self._stt_continuous = True
        if self.cfg.stt.wakeword_enabled:
            self._wakeword_state = "sleeping"
            self.icon.icon = icon_listening()
        else:
            self.icon.icon = icon_active()
        self.icon.update_menu()
        log.info("STT continuous ON")

    def _on_continuous_off(self) -> None:
        """Called by key listener when continuous mode turns OFF."""
        self._stt_continuous = False
        self._wakeword_state = "sleeping"
        self.icon.icon = icon_inactive()
        self.icon.update_menu()
        log.info("STT continuous OFF")

    def _on_wake_state_changed(self, state: str) -> None:
        """Called by key listener when wake word state changes."""
        self._wakeword_state = state
        if self._stt_continuous:
            if state == "awake":
                self.icon.icon = icon_active()
            else:
                self.icon.icon = icon_listening()
            self.icon.update_menu()
        log.debug("Wake word state: %s", state)

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
            if self.cfg.stt.wakeword_enabled and self._wakeword_state != "awake":
                self.icon.icon = icon_listening()
            else:
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
        import json

        # Silence httpx INFO logs from repeated health checks
        logging.getLogger("httpx").setLevel(logging.WARNING)

        from claudible.tts.client import TTSClient

        client = TTSClient(base_url=f"http://{self.cfg.tts.host}:{self.cfg.tts.port}")
        while not self._health_stop.is_set():
            try:
                healthy = asyncio.run(client.health())
            except Exception:
                healthy = False
            changed = healthy != self._server_healthy
            self._server_healthy = healthy

            # Poll wake word state from file + enforce timeout
            if self._stt_continuous and self.cfg.stt.wakeword_enabled:
                try:
                    with open(WAKEWORD_STATE, "r") as f:
                        wake_data = json.load(f)
                    ws = wake_data.get("state", "sleeping")
                    # Enforce timeout: if awake too long with no input, force back to sleeping
                    if ws == "awake" and self.cfg.stt.wakeword_timeout > 0:
                        import time
                        activated_at = wake_data.get("activated_at", 0.0)
                        if time.time() - activated_at > self.cfg.stt.wakeword_timeout:
                            ws = "sleeping"
                            # Write sleeping state back to file
                            wake_data["state"] = "sleeping"
                            wake_data["activated_at"] = 0.0
                            tmp = str(WAKEWORD_STATE) + ".tmp"
                            with open(tmp, "w") as f:
                                json.dump(wake_data, f)
                            os.rename(tmp, str(WAKEWORD_STATE))
                            log.info("Wake word timeout — forced back to sleeping")
                except (FileNotFoundError, json.JSONDecodeError, OSError):
                    ws = "sleeping"
                if ws != self._wakeword_state:
                    self._wakeword_state = ws
                    changed = True

            if changed:
                self._update_icon()
            self._health_stop.wait(5)

    def _quit(self) -> None:
        self._health_stop.set()
        self._key_stop_event.set()
        self._stop_proc_watcher()
        if self._key_thread:
            self._key_thread.join(timeout=3)
        if self._dictation.is_running:
            self._dictation.stop()
        self.icon.stop()
