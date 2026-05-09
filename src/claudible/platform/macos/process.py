"""macOS process backend — psutil-based process watching."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any

import psutil

from claudible.platform.base import ProcessBackend
from claudible.stt.windows import read_window_state, write_window_state

log = logging.getLogger(__name__)

_MY_UID = os.getuid()


class PsutilProcess(ProcessBackend):
    """psutil-based process watcher for macOS."""

    def create_watcher(
        self, config: Any, on_slots_changed: Callable[[int], None] | None = None,
    ) -> Any:
        return MacOSProcessWatcher(config, on_slots_changed=on_slots_changed)

    def scan_for_names(self, names: list[str]) -> list[dict]:
        return scan_for_names(names)

    def find_terminal_window(self, pid: int) -> int | None:
        # macOS doesn't have the same X11 window lookup
        return None


def scan_for_names(names: list[str]) -> list[dict]:
    """Scan for processes matching names using psutil."""
    results: list[dict] = []
    names_set = set(names)
    for proc in psutil.process_iter(["pid", "name", "username", "cmdline"]):
        try:
            info = proc.info
            if info["name"] in names_set and info.get("username") == os.getlogin():
                cmdline = " ".join(info.get("cmdline") or [])
                results.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cmdline": cmdline,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return results


class MacOSProcessWatcher:
    """Poll-based process watcher for macOS using psutil."""

    def __init__(
        self, config: Any, on_slots_changed: Callable[[int], None] | None = None,
    ) -> None:
        self._config = config
        self._on_slots_changed = on_slots_changed
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pid_to_slot: dict[int, str] = {}

    @property
    def watched_processes(self) -> list[str]:
        return self._config.stt.watched_processes

    @property
    def interval(self) -> float:
        return self._config.stt.process_watch_interval

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="procwatch-mac")
        self._thread.start()
        log.info("Process watcher started — watching %s", self.watched_processes)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                log.exception("Process watcher poll error")
            self._stop_event.wait(self.interval)

    def _poll(self) -> None:
        names = self.watched_processes
        if not names:
            return

        live_procs = scan_for_names(names)
        live_pids = {p["pid"] for p in live_procs}

        state = read_window_state()
        windows = state.setdefault("windows", {})
        changed = False

        # Prune dead PIDs
        dead_slots = []
        for slot, entry in list(windows.items()):
            pid = entry.get("pid")
            if pid is None:
                continue
            if not psutil.pid_exists(pid):
                dead_slots.append(slot)
                self._pid_to_slot.pop(pid, None)

        for slot in dead_slots:
            del windows[slot]
            changed = True

        # Assign new PIDs
        for proc in live_procs:
            pid = proc["pid"]
            if pid in self._pid_to_slot:
                continue

            slot = self._lowest_free_slot(windows)
            windows[slot] = {
                "window_id": pid,  # Use PID as pseudo window ID on macOS
                "title": proc["name"],
                "pid": pid,
                "process": proc["name"],
            }
            self._pid_to_slot[pid] = slot
            changed = True

        if changed:
            write_window_state(state)
            if self._on_slots_changed:
                try:
                    self._on_slots_changed(len(windows))
                except Exception:
                    log.debug("on_slots_changed callback error", exc_info=True)

    @staticmethod
    def _lowest_free_slot(windows: dict) -> str:
        i = 1
        while str(i) in windows:
            i += 1
        return str(i)
