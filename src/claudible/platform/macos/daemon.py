"""macOS daemon backend — launchd plist management."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from claudible.platform.base import DaemonBackend

log = logging.getLogger(__name__)

PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_NAME = "com.claudible.agent"
PLIST_FILE = PLIST_DIR / f"{PLIST_NAME}.plist"

PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>claudible.cli</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_dir}/claudible.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/claudible.err</string>
</dict>
</plist>
"""


class LaunchdDaemon(DaemonBackend):
    """launchd-based service management for macOS."""

    def _ensure_plist(self) -> None:
        """Create the plist file if it doesn't exist."""
        if PLIST_FILE.exists():
            return
        PLIST_DIR.mkdir(parents=True, exist_ok=True)
        log_dir = Path.home() / "Library" / "Logs" / "claudible"
        log_dir.mkdir(parents=True, exist_ok=True)
        content = PLIST_TEMPLATE.format(
            label=PLIST_NAME,
            python=sys.executable,
            log_dir=str(log_dir),
        )
        PLIST_FILE.write_text(content)
        log.info("Created launchd plist: %s", PLIST_FILE)

    def is_service_available(self) -> bool:
        return True  # launchctl is always available on macOS

    def is_service_enabled(self) -> bool:
        if not PLIST_FILE.exists():
            return False
        try:
            result = subprocess.run(
                ["launchctl", "list", PLIST_NAME],
                capture_output=True, text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def start_service(self) -> bool:
        self._ensure_plist()
        try:
            subprocess.run(
                ["launchctl", "load", str(PLIST_FILE)],
                check=True,
            )
            subprocess.run(
                ["launchctl", "start", PLIST_NAME],
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def stop_service(self) -> bool:
        try:
            subprocess.run(
                ["launchctl", "stop", PLIST_NAME],
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
