"""PID file management for singleton enforcement."""

from __future__ import annotations

import logging
import os
import signal
import time

from claudible.paths import CACHE_DIR, PID_FILE

log = logging.getLogger(__name__)


def write_pid() -> None:
    """Write the current process PID to the PID file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    log.debug("Wrote PID %d to %s", os.getpid(), PID_FILE)


def read_pid() -> int | None:
    """Read PID from file, return None if missing or invalid."""
    try:
        return int(PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def is_running() -> bool:
    """Check if a claudible process is alive based on the PID file."""
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        # Stale PID file — process is gone
        remove_pid()
        return False
    except PermissionError:
        # Process exists but we can't signal it (shouldn't happen for own user)
        return True


def remove_pid() -> None:
    """Remove the PID file if it exists."""
    try:
        PID_FILE.unlink()
        log.debug("Removed PID file %s", PID_FILE)
    except FileNotFoundError:
        pass


def stop_running() -> bool:
    """Send SIGTERM to the running process and wait up to 5s for it to exit.

    Returns True if the process was stopped, False if nothing was running.
    """
    pid = read_pid()
    if pid is None:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        remove_pid()
        return False

    log.info("Sending SIGTERM to PID %d", pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        remove_pid()
        return True

    # Wait up to 5 seconds for exit
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            remove_pid()
            return True
        time.sleep(0.1)

    # Still alive after 5s
    log.warning("PID %d did not exit after 5s", pid)
    remove_pid()
    return True
