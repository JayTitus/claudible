"""Claude Code stop hook — reads assistant message from stdin and sends to TTS.

This script is invoked by Claude Code's hook system after each assistant response.
It reads the hook event JSON from stdin, extracts the last assistant message,
optionally rephrases it, and fires it to the TTS server (non-blocking).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

log = logging.getLogger(__name__)


def _extract_text(hook_data: dict) -> str | None:
    """Extract the assistant's text from the hook event data."""
    # Claude Code stop hook provides: {"type": "stop", "stop_reason": "...",
    #   "last_assistant_message": "..."}
    text = hook_data.get("last_assistant_message")
    if not text:
        # Try alternate structures
        message = hook_data.get("message", {})
        if isinstance(message, dict):
            text = message.get("content", "")
    if isinstance(text, str):
        text = text.strip()
    return text if text else None


async def _process(text: str) -> None:
    """Rephrase (if enabled) and send to TTS server."""
    from claudible.config import Config
    from claudible.rephrase.ollama import rephrase
    from claudible.tts.client import TTSClient

    cfg = Config.load()
    if cfg.rephrase.enabled:
        text = await rephrase(text, cfg)

    client = TTSClient(
        base_url=f"http://{cfg.tts.host}:{cfg.tts.port}",
        timeout=cfg.tts.speed * 30,
    )
    await client.speak(text, voice=cfg.tts.voice, language=cfg.tts.language, speed=cfg.tts.speed)


async def _announce_completion() -> None:
    """Speak a completion announcement when extract_speakable() filtered everything."""
    from claudible.config import Config
    from claudible.tts.client import TTSClient

    cfg = Config.load()
    if cfg.completion.mode == "none":
        return

    text = None

    if cfg.completion.mode == "persona" and cfg.rephrase.enabled:
        from claudible.rephrase.ollama import generate_completion_quip

        quip = await generate_completion_quip(cfg)
        if quip:
            prefix = cfg.completion.persona_prefix.strip()
            text = f"{prefix} {quip}".strip() if prefix else quip

    if not text:
        text = cfg.completion.simple_phrase

    client = TTSClient(
        base_url=f"http://{cfg.tts.host}:{cfg.tts.port}",
        timeout=cfg.tts.speed * 30,
    )
    await client.speak(text, voice=cfg.tts.voice, language=cfg.tts.language, speed=cfg.tts.speed)


def main() -> None:
    """Entry point for the stop hook."""
    from claudible.paths import TTS_MUTE_FLAG

    if TTS_MUTE_FLAG.exists():
        return

    try:
        raw = sys.stdin.read()
        if not raw:
            return
        data = json.loads(raw)
        text = _extract_text(data)
        if not text:
            return

        # Filter to only conversational content — skip code, commands, output
        from claudible.hooks.filter import extract_speakable

        text = extract_speakable(text)
        if not text:
            asyncio.run(_announce_completion())
            return

        # Truncate very long responses to keep TTS reasonable
        if len(text) > 2000:
            text = text[:2000] + "... truncated."

        asyncio.run(_process(text))
    except Exception:
        # Hooks must never crash Claude Code — fail silently
        log.debug("Stop hook error", exc_info=True)


if __name__ == "__main__":
    main()
