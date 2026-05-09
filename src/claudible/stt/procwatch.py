"""Process-based window lock — watches /proc for target CLI tools (Linux only)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from collections.abc import Callable

from claudible.config import Config
from claudible.stt.windows import read_window_state, write_window_state

log = logging.getLogger(__name__)

_MY_UID = os.getuid() if sys.platform != "win32" else 0


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


def _get_process_tty(pid: int) -> str | None:
    """Get the controlling TTY device for a PID (e.g. '/dev/pts/2')."""
    try:
        fd0 = os.readlink(f"/proc/{pid}/fd/0")
        if fd0.startswith("/dev/pts/"):
            return fd0
    except OSError:
        pass
    return None


def _resolve_konsole_session(target_pid: int, konsole_pid: int) -> dict | None:
    """Find the Konsole D-Bus session that owns *target_pid*.

    Matches by comparing PTY devices: the target process's /dev/pts/N
    must match the PTY of one of Konsole's session shell PIDs.

    Returns dict with konsole_service, konsole_session, or None.
    """
    target_tty = _get_process_tty(target_pid)
    if not target_tty:
        return None

    service = f"org.kde.konsole-{konsole_pid}"

    # Enumerate sessions by introspecting /Sessions
    try:
        xml = subprocess.check_output(
            ["qdbus", service, "/Sessions",
             "org.freedesktop.DBus.Introspectable.Introspect"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    import re
    session_ids = re.findall(r'<node name="(\d+)"', xml)

    for sid in session_ids:
        try:
            shell_pid_str = subprocess.check_output(
                ["qdbus", service, f"/Sessions/{sid}",
                 "org.kde.konsole.Session.processId"],
                stderr=subprocess.DEVNULL, timeout=2,
            ).decode().strip()
            shell_pid = int(shell_pid_str)
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired, ValueError):
            continue

        shell_tty = _get_process_tty(shell_pid)
        if shell_tty == target_tty:
            return {
                "konsole_service": service,
                "konsole_session": f"/Sessions/{sid}",
            }

    return None


def find_terminal_info(pid: int) -> dict | None:
    """Walk the parent chain of *pid* looking for a terminal emulator.

    Returns a dict with terminal details for the nerd-dictation callback:
      - terminal: terminal emulator name (e.g. "konsole", "alacritty")
      - terminal_pid: PID of the terminal emulator process
      - window_id: X11 window ID (may be None on Wayland)
      - konsole_service: Konsole D-Bus service name (Konsole only)
      - konsole_session: Konsole D-Bus session path (Konsole only)

    IDE terminals (VS Code, JetBrains) are skipped.
    Returns None if no supported terminal is found.
    """
    visited: set[int] = set()
    current = pid
    while current > 1 and current not in visited:
        visited.add(current)
        comm = _read_comm(current)

        if comm in _TERMINAL_EMULATORS:
            result: dict = {
                "terminal": comm,
                "terminal_pid": current,
                "window_id": None,
            }

            # Try to get X11 window ID
            try:
                out = subprocess.check_output(
                    ["xdotool", "search", "--pid", str(current)],
                    stderr=subprocess.DEVNULL, timeout=3,
                ).decode().strip()
                if out:
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
                    result["window_id"] = best_wid
            except (FileNotFoundError, subprocess.CalledProcessError,
                    subprocess.TimeoutExpired, ValueError):
                pass

            # For Konsole: resolve the exact D-Bus session
            if comm == "konsole":
                session_info = _resolve_konsole_session(pid, current)
                if session_info:
                    result.update(session_info)

            return result

        # Walk to parent
        try:
            with open(f"/proc/{current}/stat", "r") as f:
                stat_line = f.read()
            close_paren = stat_line.rfind(")")
            fields_after_comm = stat_line[close_paren + 2:].split()
            ppid = int(fields_after_comm[1])
            current = ppid
        except (OSError, IndexError, ValueError):
            break

    return None


def find_terminal_window(pid: int) -> int | None:
    """Legacy wrapper — returns just the window ID for backwards compat."""
    info = find_terminal_info(pid)
    return info["window_id"] if info else None


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

            term_info = find_terminal_info(pid)
            if term_info is None:
                continue  # No supported terminal found

            window_id = term_info.get("window_id")

            # Check if this window_id already has a slot (same terminal, new process)
            if window_id is not None:
                existing_slot = wid_to_slot.get(window_id)
                if existing_slot is not None:
                    old_pid = windows[existing_slot].get("pid")
                    windows[existing_slot]["pid"] = pid
                    windows[existing_slot]["process"] = proc["name"]
                    # Update terminal session info (session may have changed)
                    if "konsole_service" in term_info:
                        windows[existing_slot]["konsole_service"] = term_info["konsole_service"]
                        windows[existing_slot]["konsole_session"] = term_info["konsole_session"]
                    windows[existing_slot]["terminal"] = term_info.get("terminal", "")
                    self._pid_to_slot.pop(old_pid, None) if old_pid else None
                    self._pid_to_slot[pid] = existing_slot
                    changed = True
                    session = term_info.get("konsole_session", "")
                    log.info(
                        "Process watcher: updated slot %s — %s (PID %d) in %s%s",
                        existing_slot, proc["name"], pid,
                        term_info["terminal"],
                        f" {session}" if session else "",
                    )
                    continue

            # Assign lowest free slot
            slot = self._lowest_free_slot(windows)
            title = get_window_title(window_id) if window_id else "(no window)"
            entry = {
                "window_id": window_id,
                "title": title,
                "pid": pid,
                "process": proc["name"],
                "terminal": term_info.get("terminal", ""),
            }
            if "konsole_service" in term_info:
                entry["konsole_service"] = term_info["konsole_service"]
                entry["konsole_session"] = term_info["konsole_session"]
            windows[slot] = entry
            if window_id is not None:
                wid_to_slot[window_id] = slot
            self._pid_to_slot[pid] = slot
            changed = True
            session = term_info.get("konsole_session", "")
            log.info(
                "Process watcher: assigned slot %s — %s (PID %d) → %s%s (%s)",
                slot, proc["name"], pid,
                term_info["terminal"],
                f" {session}" if session else "",
                title,
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
