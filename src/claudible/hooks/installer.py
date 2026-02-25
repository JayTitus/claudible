"""Install/uninstall Claude Code hooks for claudible."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

HOOKS_DIR = Path.home() / ".claude"
HOOKS_FILE = HOOKS_DIR / "hooks.json"

HOOK_ENTRY = {
    "type": "stop",
    "command": "python -m claudible.hooks.stop_hook",
    "description": "Claudible TTS — speaks Claude's responses",
}


def install_hook() -> bool:
    """Add the claudible stop hook to Claude Code's hooks.json."""
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    hooks = _load_hooks()
    stop_hooks = hooks.setdefault("hooks", {}).setdefault("stop", [])

    # Check if already installed
    for h in stop_hooks:
        if "claudible" in h.get("command", ""):
            log.info("Claudible hook already installed")
            return True

    stop_hooks.append(HOOK_ENTRY)
    _save_hooks(hooks)
    log.info("Claudible stop hook installed")
    return True


def uninstall_hook() -> bool:
    """Remove the claudible stop hook from Claude Code's hooks.json."""
    if not HOOKS_FILE.exists():
        return True

    hooks = _load_hooks()
    stop_hooks = hooks.get("hooks", {}).get("stop", [])
    original_len = len(stop_hooks)

    stop_hooks[:] = [h for h in stop_hooks if "claudible" not in h.get("command", "")]

    if len(stop_hooks) < original_len:
        _save_hooks(hooks)
        log.info("Claudible stop hook removed")
    return True


def is_installed() -> bool:
    """Check if the claudible hook is installed."""
    if not HOOKS_FILE.exists():
        return False
    hooks = _load_hooks()
    for h in hooks.get("hooks", {}).get("stop", []):
        if "claudible" in h.get("command", ""):
            return True
    return False


def _load_hooks() -> dict:
    if HOOKS_FILE.exists():
        return json.loads(HOOKS_FILE.read_text())
    return {}


def _save_hooks(hooks: dict) -> None:
    HOOKS_FILE.write_text(json.dumps(hooks, indent=2) + "\n")
