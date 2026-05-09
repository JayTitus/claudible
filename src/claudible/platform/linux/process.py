"""Linux process backend — delegates to stt/procwatch.py (/proc)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from claudible.platform.base import ProcessBackend


class ProcfsProcess(ProcessBackend):
    """/proc-based process watcher for Linux."""

    def create_watcher(
        self, config: Any, on_slots_changed: Callable[[int], None] | None = None,
    ) -> Any:
        from claudible.stt.procwatch import ProcessWatcher

        return ProcessWatcher(config, on_slots_changed=on_slots_changed)

    def scan_for_names(self, names: list[str]) -> list[dict]:
        from claudible.stt.procwatch import scan_proc_for_names

        return scan_proc_for_names(names)

    def find_terminal_window(self, pid: int) -> int | None:
        from claudible.stt.procwatch import find_terminal_window

        return find_terminal_window(pid)
