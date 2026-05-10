"""In-process text router for STT backends.

Holds the logic that converts a recognized text chunk into one of:
    - keystroke injection (e.g. "submit" → press Return)
    - text injection (the recognized text, possibly corrected)
    - no-op (e.g. wake-word still asleep, suppressed)

Used by any STT backend that hands us text in-process (RealtimeSTT,
direct-VOSK on macOS, etc.). The legacy nerd-dictation backend uses
:mod:`claudible.stt.callback`, which is a string-template generator
that runs in the nerd-dictation subprocess; that path is preserved
for backward compatibility but the in-process :class:`Router` is the
canonical version going forward.

The Router does not know how to talk to X11, Konsole D-Bus, AppleScript,
etc. — those concerns live in an :class:`Injector` implementation that
the router calls into. Platforms supply their own injector under
``claudible.platform.{linux,macos}.inject``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Protocol

import httpx

from claudible.config import Config
from claudible.paths import WAKEWORD_STATE, WINDOW_STATE

log = logging.getLogger(__name__)

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}

OPTION_PREFIXES = ("select", "option", "number", "choose", "pick")
DEACTIVATION_PHRASES = ("stop listening", "go to sleep", "never mind", "nevermind")
REGISTER_PREFIXES = ("register window",)


class Injector(Protocol):
    """Platform-specific keystroke / text injection.

    Implementations target a window/session resolved from a slot id.
    The router resolves slot info and calls :meth:`set_target` before
    each :meth:`send_text` / :meth:`send_key` call.
    """

    def set_target(self, target: dict) -> None:
        """Set the active target. ``target`` may include any of
        ``window_id``, ``konsole_service``, ``konsole_session``."""

    def send_text(self, text: str) -> bool:
        """Type ``text`` into the active target. Return True on success."""

    def send_key(self, key: str) -> bool:
        """Press a key by X11-style name (Return, BackSpace, Tab, Escape).
        Return True on success."""

    def get_active_window(self) -> tuple[int | None, str]:
        """Return (window_id, title) of the currently focused window,
        or (None, "") if not supported / unavailable."""

    def resolve_target(self, slot: str) -> dict:
        """Look up routing info for a slot id from the window state file.
        Returns dict with any of window_id, konsole_service, konsole_session."""


class RouterResult:
    """What :meth:`Router.process` did with a text chunk.

    ``action`` is one of:
        - "typed"     — text was injected via the injector
        - "key"       — a key was sent (e.g. Return for "submit")
        - "wake"      — wake-word activated; no other action
        - "sleep"     — wake-word deactivated; no other action
        - "register"  — voice-registered the focused window
        - "suppress"  — sleeping or otherwise dropped
    """

    __slots__ = ("action", "text", "key", "persona", "slot", "corrected")

    def __init__(
        self,
        action: str,
        text: str = "",
        key: str = "",
        persona: str = "",
        slot: str = "",
        corrected: bool = False,
    ) -> None:
        self.action = action
        self.text = text
        self.key = key
        self.persona = persona
        self.slot = slot
        self.corrected = corrected

    def __repr__(self) -> str:
        return f"RouterResult(action={self.action!r}, text={self.text!r}, key={self.key!r})"


class Router:
    """Process recognized text and route it to the active target.

    One Router instance per claudible session. It owns the wake-word
    state (mirrored to disk for the tray icon) and the active-target
    cache, and calls the supplied :class:`Injector` for I/O.
    """

    def __init__(self, config: Config, injector: Injector) -> None:
        self.config = config
        self.injector = injector
        self._last_chunk = ""
        self._active_target: dict = {}

    # ── Wake-word state (mirrored to WAKEWORD_STATE for the tray icon) ──

    @staticmethod
    def _read_wake_state() -> dict:
        try:
            with open(WAKEWORD_STATE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"state": "sleeping", "activated_at": 0.0}

    @staticmethod
    def _write_wake_state(
        state: str, activated_at: float = 0.0,
        persona: str = "", slot: str = "",
    ) -> None:
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

    # ── Window state (read-only here; injectors update it on registration) ─

    @staticmethod
    def _read_window_state() -> dict:
        try:
            with open(WINDOW_STATE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"windows": {}, "default_slot": "1"}

    @staticmethod
    def _write_window_state(state: dict) -> None:
        tmp = str(WINDOW_STATE) + ".tmp"
        try:
            os.makedirs(str(WINDOW_STATE.parent), exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(state, f)
            os.rename(tmp, str(WINDOW_STATE))
        except OSError:
            pass

    # ── Triggers and corrections ────────────────────────────────────────

    def _build_trigger_words(self) -> dict[str, str]:
        """Flatten config.rephrase.trigger_words (which may have comma
        variants) into trigger phrase → persona name."""
        result: dict[str, str] = {}
        for persona, trigger in self.config.rephrase.trigger_words.items():
            for variant in trigger.split(","):
                v = variant.strip().lower()
                if v:
                    result[v] = persona
        return result

    def _check_trigger(
        self, text: str, trigger_words: dict[str, str],
    ) -> tuple[str, str, str]:
        """Check if text starts with a trigger word.

        Supports lookback into the previous chunk for triggers split
        across two recognition results.

        Returns ``(remainder, persona, slot)`` if a trigger fires, else
        ``("", "", "")``. Slot defaults to ``"1"`` and is parsed from
        the first word after the trigger if it's a digit / number-word.
        """
        lower = text.strip().lower()
        for trigger, persona in trigger_words.items():
            t = trigger.lower()
            if lower.startswith(t):
                rem = text.strip()[len(t):].strip()
            elif self._last_chunk:
                combined = (self._last_chunk + " " + lower).strip()
                if combined.startswith(t):
                    rem = combined[len(t):].strip()
                else:
                    continue
            else:
                continue

            slot = "1"
            words = rem.lower().split() if rem else []
            if words and words[0] in NUMBER_WORDS:
                slot = NUMBER_WORDS[words[0]]
                rem = " ".join(rem.split()[1:]).strip()
            elif words and words[0].isdigit():
                slot = words[0]
                rem = " ".join(rem.split()[1:]).strip()
            return rem, persona, slot
        return "", "", ""

    def _correct(self, text: str) -> tuple[str, bool]:
        """Run the recognized text through the claudible STT corrector.

        Returns ``(corrected_text, was_changed)``. Falls back to the raw
        text on any failure.
        """
        if not self.config.correction.enabled:
            return text, False
        url = f"http://{self.config.tts.host}:{self.config.tts.port}/api/correct"
        try:
            resp = httpx.post(url, json={"text": text}, timeout=2)
            corrected = resp.json().get("text", text)
            return corrected, corrected.strip().lower() != text.strip().lower()
        except Exception:
            return text, False

    # ── Voice registration ──────────────────────────────────────────────

    def _handle_voice_registration(self, lower: str) -> bool:
        """Handle "register window [N]" voice commands."""
        for prefix in REGISTER_PREFIXES:
            if not lower.startswith(prefix):
                continue
            rest = lower[len(prefix):].strip()
            slot = "1"
            if rest in NUMBER_WORDS:
                slot = NUMBER_WORDS[rest]
            elif rest.isdigit():
                slot = rest
            wid, title = self.injector.get_active_window()
            if wid:
                state = self._read_window_state()
                state.setdefault("windows", {})[slot] = {
                    "window_id": wid,
                    "title": title,
                }
                self._write_window_state(state)
            return True
        return False

    # ── Main entry point ────────────────────────────────────────────────

    def process(self, text: str) -> RouterResult:
        """Process one chunk of recognized text.

        The router decides what to do (type, send key, register, sleep,
        suppress) and calls the injector to actually do it. Returns a
        :class:`RouterResult` describing what happened.
        """
        text = text.strip()
        if not text:
            return RouterResult(action="suppress")

        lower = text.lower()
        words = lower.split()
        keywords = self.config.dictation.keywords
        trigger_words = self._build_trigger_words()
        wake_enabled = self.config.stt.wakeword_enabled and bool(trigger_words)

        # ── Wake-word gate ──────────────────────────────────────────
        if wake_enabled:
            state = self._read_wake_state()
            now = time.time()

            if state.get("state") == "awake":
                # Refresh target from the slot we activated against
                wake_slot = state.get("slot", "1")
                self._active_target = self.injector.resolve_target(wake_slot)
                self.injector.set_target(self._active_target)

                # Idle timeout
                timeout = self.config.stt.wakeword_timeout
                activated_at = state.get("activated_at", 0.0)
                if timeout > 0 and (now - activated_at) > timeout:
                    self._write_wake_state("sleeping")
                    self._active_target = {}
                    self._last_chunk = lower
                    return RouterResult(action="sleep")

                # Refresh activation time
                self._write_wake_state(
                    "awake", now, state.get("persona", ""), wake_slot,
                )

                # Voice registration commands
                if self._handle_voice_registration(lower):
                    return RouterResult(action="register")

                # Deactivation phrases
                for phrase in DEACTIVATION_PHRASES:
                    if phrase in lower:
                        self._write_wake_state("sleeping")
                        self._last_chunk = ""
                        self._active_target = {}
                        if "submit" in lower:
                            self.injector.send_key("Return")
                            return RouterResult(action="key", key="Return")
                        return RouterResult(action="sleep")

                # fall through to keyword/option/text processing

            else:
                # Sleeping: scan for a trigger word
                rem, persona, slot = self._check_trigger(text, trigger_words)
                if rem or persona:
                    self._write_wake_state("awake", now, persona, slot)
                    self._active_target = self.injector.resolve_target(slot)
                    self.injector.set_target(self._active_target)
                    self._last_chunk = ""
                    if rem:
                        text = rem
                        lower = text.lower()
                        words = lower.split()
                        # fall through and handle the remainder
                    else:
                        return RouterResult(
                            action="wake", persona=persona, slot=slot,
                        )
                else:
                    self._last_chunk = lower
                    return RouterResult(action="suppress")
        else:
            # No wake word: resolve default slot if window-locked
            if self.config.stt.window_lock_enabled:
                self._active_target = self.injector.resolve_target("1")
            else:
                self._active_target = {}
            self.injector.set_target(self._active_target)

        # ── Keyword commands ────────────────────────────────────────
        if len(words) == 1 and lower in keywords:
            key = keywords[lower]
            self.injector.send_key(key)
            # "submit"/"enter" while wake word active → also go to sleep
            if wake_enabled and key == "Return":
                self._write_wake_state("sleeping")
                self._active_target = {}
                self._last_chunk = ""
            return RouterResult(action="key", key=key)

        # ── Option selection: "select 2", "option three", etc. ───────
        if len(words) == 2 and words[0] in OPTION_PREFIXES:
            digit_word = words[1]
            digit = digit_word if digit_word.isdigit() else NUMBER_WORDS.get(digit_word, "")
            if digit:
                self.injector.send_text(digit)
                time.sleep(0.05)
                self.injector.send_key("Return")
                return RouterResult(action="typed", text=digit)

        # ── Normal dictation: correct, then type ─────────────────────
        corrected, was_changed = self._correct(text)
        self.injector.send_text(corrected)
        self._last_chunk = lower
        return RouterResult(action="typed", text=corrected, corrected=was_changed)
