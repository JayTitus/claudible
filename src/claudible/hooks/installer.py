"""Install/uninstall Claude Code hooks for claudible."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SETTINGS_FILE = Path.home() / ".claude" / "settings.json"

def _hook_command() -> str:
    """Build the hook command using the current Python interpreter."""
    import sys
    return f"{sys.executable} -m claudible.hooks.stop_hook"


HOOK_ENTRY_TEMPLATE = {
    "type": "command",
}


def install_hook() -> bool:
    """Add the claudible stop hook to Claude Code's settings.json."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    settings = _load_settings()
    hooks = settings.setdefault("hooks", {})
    stop_list = hooks.setdefault("Stop", [])

    # Check if already installed
    for entry in stop_list:
        for h in entry.get("hooks", []):
            if "claudible" in h.get("command", ""):
                log.info("Claudible hook already installed")
                return True

    entry = {**HOOK_ENTRY_TEMPLATE, "command": _hook_command()}
    stop_list.append({
        "matcher": "",
        "hooks": [entry],
    })
    _save_settings(settings)
    log.info("Claudible stop hook installed")
    return True


def uninstall_hook() -> bool:
    """Remove the claudible stop hook from Claude Code's settings.json."""
    if not SETTINGS_FILE.exists():
        return True

    settings = _load_settings()
    stop_list = settings.get("hooks", {}).get("Stop", [])
    original_len = len(stop_list)

    stop_list[:] = [
        entry for entry in stop_list
        if not any("claudible" in h.get("command", "") for h in entry.get("hooks", []))
    ]

    if len(stop_list) < original_len:
        _save_settings(settings)
        log.info("Claudible stop hook removed")
    return True


def is_installed() -> bool:
    """Check if the claudible hook is installed."""
    if not SETTINGS_FILE.exists():
        return False
    settings = _load_settings()
    for entry in settings.get("hooks", {}).get("Stop", []):
        for h in entry.get("hooks", []):
            if "claudible" in h.get("command", ""):
                return True
    return False


def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {}


def _save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")
