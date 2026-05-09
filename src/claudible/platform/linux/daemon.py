"""Linux daemon backend — systemd service management."""

from __future__ import annotations

import shutil
import subprocess

from claudible.platform.base import DaemonBackend


class SystemdDaemon(DaemonBackend):
    """systemd user service management for Linux."""

    def is_service_available(self) -> bool:
        return shutil.which("systemctl") is not None

    def is_service_enabled(self) -> bool:
        if not self.is_service_available():
            return False
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", "claudible"],
                capture_output=True, text=True,
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def start_service(self) -> bool:
        try:
            subprocess.run(
                ["systemctl", "--user", "start", "claudible"],
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def stop_service(self) -> bool:
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", "claudible"],
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
