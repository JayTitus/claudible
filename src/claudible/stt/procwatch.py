"""Process-based window lock — watches /proc for target CLI tools."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from collections.abc import Callable

from claudible.config import Config
from claudible.stt.windows import read_window_state, write_window_state

log = logging.getLogger(__name__)

_MY_UID = os.getuid()


def scan_proc_for_names(names: list[str]) -> list[dict]:
    """Scan /proc for processes matching *names*, filtered to current UID.

    Returns list of ``{"pid": int, "name": str, "cmdline": str}``.
    """
    results: list[dict] = []
    names_set = set(names)
    try:
        entries = os.listdir("/proc")
    except OSError:
        return results

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        proc = f"/proc/{pid}"
        try:
            # Check ownership via /proc/<pid>/status UID line
            stat = os.stat(proc)
            if stat.st_uid != _MY_UID:
                continue
            # Read comm (process name, max 16 chars, no path)
            with open(f"{proc}/comm", "r") as f:
                comm = f.read().strip()
            if comm not in names_set:
                continue
            # Skip background processes (no controlling terminal) —
            # filters out VS Code extension backends, app-servers, etc.
            # tty_nr is field 7 (0-indexed after comm) in /proc/<pid>/stat
            with open(f"{proc}/stat", "r") as f:
                stat_line = f.read()
            close_paren = stat_line.rfind(")")
            stat_fields = stat_line[close_paren + 2:].split()
            tty_nr = int(stat_fields[4])  # field index 4 after comm = tty_nr
            if tty_nr == 0:
                continue
            # Read full cmdline for extra context
            with open(f"{proc}/cmdline", "r") as f:
                cmdline = f.read().replace("\0", " ").strip()
            results.append({"pid": pid, "name": comm, "cmdline": cmdline})
        except (OSError, PermissionError):
            continue

    return results


def _get_window_size(window_id: int) -> tuple[int, int]:
    """Get the width and height of an X11 window via xdotool."""
    try:
        out = subprocess.check_output(
            ["xdotool", "getwindowgeometry", str(window_id)],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
        # Output format: "  Geometry: 1720x1396"
        for line in out.splitlines():
            if "Geometry:" in line:
                dims = line.split("Geometry:")[1].strip()
                w, h = dims.split("x")
                return int(w), int(h)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        pass
    return 0, 0


# Minimum dimensions to consider a window "real" (skip helper/utility windows)
_MIN_WINDOW_SIZE = 300

# Terminal emulator process names (comm values) that support xdotool input
# when unfocused.  IDE integrated terminals (VS Code, JetBrains, etc.) do NOT
# work because xdotool targets the IDE window, not the internal terminal widget.
_TERMINAL_EMULATORS = frozenset({
    "konsole",
    "gnome-terminal-",  # gnome-terminal comm is truncated to 15 chars
    "alacritty",
    "kitty",
    "wezterm-gui",
    "xterm",
    "urxvt",
    "xfce4-terminal",
    "mate-terminal",
    "tilix",
    "terminator",
    "sakura",
    "terminology",
    "st",
    "foot",           # foot runs on Wayland but also X11
    "lxterminal",
    "qterminal",
    "guake",
    "yakuake",
    "tilda",
    "cool-retro-term",
    "tabby",
    "hyper",
    "rio",
    "ghostty",
})


def _read_comm(pid: int) -> str:
    """Read the comm (short process name) for a PID."""
    try:
        with open(f"/proc/{pid}/comm", "r") as f:
            return f.read().strip()
    except OSError:
        return ""


def find_terminal_window(pid: int) -> int | None:
    """Walk the parent chain of *pid* via /proc looking for a terminal emulator window.

    Only matches windows owned by known terminal emulators (Konsole, Alacritty,
    etc.).  IDE integrated terminals (VS Code, JetBrains) are skipped because
    xdotool cannot target their internal terminal widgets — input goes to
    whatever element has focus in the IDE, not the terminal pane.

    Returns the first real (>= 300x300) X11 window ID found under a terminal
    emulator process, or None on Wayland/failure/IDE-only.
    """
    visited: set[int] = set()
    current = pid
    while current > 1 and current not in visited:
        visited.add(current)

        # Read the process name at this level
        comm = _read_comm(current)

        # Only look for windows if this process is a terminal emulator
        if comm in _TERMINAL_EMULATORS:
            try:
                out = subprocess.check_output(
                    ["xdotool", "search", "--pid", str(current)],
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                ).decode().strip()
                if out:
                    # Collect all real windows and pick the largest one
                    # (terminal emulators like Konsole have multiple X11
                    # windows — sub-panels, toolbars, etc. — the main
                    # terminal is always the biggest)
                    best_wid = None
                    best_area = 0
                    for line in out.splitlines():
                        try:
                            wid = int(line)
                        except ValueError:
                            continue
                        w, h = _get_window_size(wid)
                        area = w * h
                        if w >= _MIN_WINDOW_SIZE and h >= _MIN_WINDOW_SIZE and area > best_area:
                            best_wid = wid
                            best_area = area
                    if best_wid is not None:
                        return best_wid
            except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
                pass

        # Walk to parent via /proc/<pid>/stat — field 4 is PPID
        try:
            with open(f"/proc/{current}/stat", "r") as f:
                stat_line = f.read()
            close_paren = stat_line.rfind(")")
            fields_after_comm = stat_line[close_paren + 2:].split()
            ppid = int(fields_after_comm[1])  # field index 1 after comm = PPID
            current = ppid
        except (OSError, IndexError, ValueError):
            break

    return None


def get_window_title(window_id: int) -> str:
    """Get the title of an X11 window via xdotool."""
    try:
        return subprocess.check_output(
            ["xdotool", "getwindowname", str(window_id)],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "(unknown)"


def _pid_alive(pid: int) -> bool:
    """Check if a PID is still alive via /proc."""
    return os.path.isdir(f"/proc/{pid}")


class ProcessWatcher:
    """Daemon thread that polls /proc for watched process names and auto-assigns window slots."""

    def __init__(self, config: Config, on_slots_changed: Callable[[int], None] | None = None) -> None:
        self._config = config
        self._on_slots_changed = on_slots_changed  # called with current slot count
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pid_to_slot: dict[int, str] = {}  # pid → slot key

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
        self._thread = threading.Thread(target=self._run, daemon=True, name="procwatch")
        self._thread.start()
        log.info("Process watcher started — watching %s every %.1fs", self.watched_processes, self.interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log.info("Process watcher stopped")

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

        live_procs = scan_proc_for_names(names)
        live_pids = {p["pid"] for p in live_procs}

        state = read_window_state()
        windows = state.setdefault("windows", {})
        changed = False

        # 1. Prune dead PIDs from tracked slots (only auto-assigned ones with pid field)
        dead_slots = []
        for slot, entry in list(windows.items()):
            pid = entry.get("pid")
            if pid is None:
                continue  # manual registration — never prune
            if not _pid_alive(pid):
                dead_slots.append(slot)
                self._pid_to_slot.pop(pid, None)

        for slot in dead_slots:
            del windows[slot]
            changed = True
            log.info("Process watcher: pruned dead slot %s", slot)

        # 2. Build reverse map: window_id → slot (for detecting same-terminal reuse)
        wid_to_slot: dict[int, str] = {}
        for slot, entry in windows.items():
            wid = entry.get("window_id")
            if wid is not None:
                wid_to_slot[wid] = slot

        # 3. Assign new PIDs
        for proc in live_procs:
            pid = proc["pid"]
            if pid in self._pid_to_slot:
                continue  # already tracked

            window_id = find_terminal_window(pid)
            if window_id is None:
                continue  # Wayland or no window found

            # Check if this window_id already has a slot (same terminal, new process)
            existing_slot = wid_to_slot.get(window_id)
            if existing_slot is not None:
                # Update PID tracking on existing slot
                old_pid = windows[existing_slot].get("pid")
                windows[existing_slot]["pid"] = pid
                windows[existing_slot]["process"] = proc["name"]
                self._pid_to_slot.pop(old_pid, None) if old_pid else None
                self._pid_to_slot[pid] = existing_slot
                changed = True
                log.info(
                    "Process watcher: updated slot %s — %s (PID %d) in existing window %d",
                    existing_slot, proc["name"], pid, window_id,
                )
                continue

            # Assign lowest free slot
            slot = self._lowest_free_slot(windows)
            title = get_window_title(window_id)
            windows[slot] = {
                "window_id": window_id,
                "title": title,
                "pid": pid,
                "process": proc["name"],
            }
            wid_to_slot[window_id] = slot
            self._pid_to_slot[pid] = slot
            changed = True
            log.info(
                "Process watcher: assigned slot %s — %s (PID %d) → window %d (%s)",
                slot, proc["name"], pid, window_id, title,
            )

        if changed:
            write_window_state(state)
            if self._on_slots_changed:
                try:
                    self._on_slots_changed(len(windows))
                except Exception:
                    log.debug("on_slots_changed callback error", exc_info=True)

    @staticmethod
    def _lowest_free_slot(windows: dict) -> str:
        """Return the lowest unused integer slot as a string."""
        i = 1
        while str(i) in windows:
            i += 1
        return str(i)
