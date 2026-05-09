"""Extracted text processing logic for STT.

This module contains the text processing pipeline (keyword shortcuts, wake words,
option selection, STT correction) as importable Python functions. Used by the
macOS direct-VOSK engine which runs in-process (no nerd-dictation callback).

The Linux nerd-dictation callback (callback.py) has its own embedded copy of
this logic to avoid import dependencies. This module is the canonical version.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from claudible.config import Config
from claudible.paths import WAKEWORD_STATE

log = logging.getLogger(__name__)

# Number word → digit
NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}

OPTION_PREFIXES = ("select", "option", "number", "choose", "pick")
DEACTIVATION_PHRASES = ("stop listening", "go to sleep", "never mind", "nevermind")

_last_chunk = ""


def _read_wake_state() -> dict:
    try:
        with open(WAKEWORD_STATE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"state": "sleeping", "activated_at": 0.0}


def _write_wake_state(state: str, activated_at: float = 0.0, persona: str = "", slot: str = "") -> None:
    import os
    data = {"state": state, "activated_at": activated_at}
    if persona:
        data["persona"] = persona
    if slot:
        data["slot"] = slot
    tmp = str(WAKEWORD_STATE) + ".tmp"
    try:
        os.makedirs(str(WAKEWORD_STATE.parent), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.rename(tmp, str(WAKEWORD_STATE))
    except OSError:
        pass


def _correct_via_server(text: str, config: Config) -> str:
    """POST text to the claudible server for STT correction."""
    if not config.correction.enabled:
        return text
    url = f"http://{config.tts.host}:{config.tts.port}/api/correct"
    try:
        resp = httpx.post(url, json={"text": text}, timeout=2)
        return resp.json().get("text", text)
    except Exception:
        return text


def _check_trigger(text: str, trigger_words: dict[str, str]) -> tuple[str, str, str]:
    """Check if text starts with a trigger word.

    Returns (remainder, persona, slot) or ("", "", "").
    """
    global _last_chunk
    lower = text.strip().lower()

    for trigger, persona in trigger_words.items():
        trigger_lower = trigger.lower()

        if lower.startswith(trigger_lower):
            remainder = text.strip()[len(trigger_lower):].strip()
        elif _last_chunk and (_last_chunk + " " + lower).strip().startswith(trigger_lower):
            combined = (_last_chunk + " " + lower).strip()
            remainder = combined[len(trigger_lower):].strip()
        else:
            continue

        # Parse slot number from remainder
        slot = "1"
        rem_words = remainder.lower().split() if remainder else []
        if rem_words and rem_words[0] in NUMBER_WORDS:
            slot = NUMBER_WORDS[rem_words[0]]
            remainder = " ".join(remainder.split()[1:]).strip()
        elif rem_words and rem_words[0].isdigit():
            slot = rem_words[0]
            remainder = " ".join(remainder.split()[1:]).strip()

        return remainder, persona, slot

    return "", "", ""


def process_text(text: str, config: Config) -> str:
    """Process recognized text through the claudible pipeline.

    Returns the text to type, or empty string to suppress.
    """
    global _last_chunk
    lower = text.strip().lower()
    words = lower.split()
    keywords = config.dictation.keywords

    # Build trigger words
    trigger_words: dict[str, str] = {}
    for persona, trigger in config.rephrase.trigger_words.items():
        for variant in trigger.split(","):
            variant = variant.strip().lower()
            if variant:
                trigger_words[variant] = persona

    wakeword_enabled = config.stt.wakeword_enabled

    # Wake word gate
    if wakeword_enabled and trigger_words:
        state = _read_wake_state()
        now = time.time()

        if state.get("state") == "awake":
            timeout = config.stt.wakeword_timeout
            activated_at = state.get("activated_at", 0.0)

            if timeout > 0 and (now - activated_at) > timeout:
                _write_wake_state("sleeping")
                _last_chunk = lower
                return ""

            _write_wake_state("awake", now, state.get("persona", ""), state.get("slot", "1"))

            for phrase in DEACTIVATION_PHRASES:
                if phrase in lower:
                    _write_wake_state("sleeping")
                    _last_chunk = ""
                    return ""
        else:
            remainder, persona, slot = _check_trigger(text, trigger_words)
            if remainder or persona:
                _write_wake_state("awake", now, persona, slot)
                _last_chunk = ""
                if remainder:
                    text = remainder
                    lower = text.strip().lower()
                    words = lower.split()
                else:
                    return ""
            else:
                _last_chunk = lower
                return ""

    # Keyword check
    if len(words) == 1 and lower in keywords:
        _last_chunk = lower
        return ""  # Keyword action handled elsewhere on macOS

    # Option selection
    if len(words) == 2 and words[0] in OPTION_PREFIXES:
        digit = words[1]
        if digit.isdigit() or digit in NUMBER_WORDS:
            _last_chunk = lower
            return ""  # Option action handled elsewhere on macOS

    # STT correction
    text = _correct_via_server(text, config)

    _last_chunk = lower
    return text
