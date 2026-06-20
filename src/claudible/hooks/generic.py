"""Generic output webhook — runtime-agnostic input path for the TTS daemon.

The legacy Claude Code stop hook (:mod:`claudible.hooks.stop_hook`) is a
thin client over the same in-process logic exposed here. New runtime
integrations (Ollama, Foundry Local, OpenWebUI, generic CLI tools) call
the HTTP endpoint ``POST /api/v1/hook/output`` defined in
:mod:`claudible.web.router`, which in turn delegates to :func:`process_output`.

The request body is intentionally narrow and easy to produce from a shell
wrapper, a userscript, or a downstream provider wrapper:

.. code-block:: json

    {
      "tool":     "ollama",                  // free-form id of source runtime
      "content":  "Hi! Done compiling.",      // text to (filter, rephrase, speak)
      "persona":  "noir",                     // optional override of active persona
      "voice":    "casey",                    // optional override of TTS voice
      "mode":     "full" | "questions" | "completion",  // optional, default from config
      "urgent":   false                        // optional — bypass speaking queue (future)
    }
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)


async def process_output(
    *,
    tool: str,
    content: str,
    persona: str | None = None,
    voice: str | None = None,
    mode: str | None = None,
    urgent: bool = False,
) -> dict[str, Any]:
    """Filter + optionally rephrase + speak.

    Returns a small status dict describing what happened so the caller can
    log it. Never raises on speech failure — the spoken output is best-effort.
    """
    from claudible.config import Config
    from claudible.hooks.filter import extract_speakable
    from claudible.rephrase.ollama import rephrase
    from claudible.tts.client import TTSClient

    if not content.strip():
        return {"ok": False, "reason": "empty content"}

    cfg = Config.load()
    effective_mode = mode or cfg.hook.mode

    # "off" — caller asked us not to speak.
    if effective_mode == "off":
        return {"ok": False, "reason": "mode=off"}

    # Filter (strip code blocks, command output, etc.)
    speakable = extract_speakable(content)
    if not speakable:
        return {"ok": False, "reason": "filtered empty"}

    # Optional rephrase through active persona (or per-call override)
    used_persona = persona or cfg.rephrase.persona
    if cfg.rephrase.enabled:
        original_persona = cfg.rephrase.persona
        try:
            if persona:
                cfg.rephrase.persona = persona
            speakable = await rephrase(speakable, cfg)
        finally:
            cfg.rephrase.persona = original_persona

    used_voice = (
        voice
        or cfg.rephrase.persona_voices.get(used_persona)
        or cfg.tts.voice
    )

    client = TTSClient(
        base_url=f"http://{cfg.tts.host}:{cfg.tts.port}",
        timeout=cfg.tts.speed * 30,
    )
    try:
        await client.speak(
            speakable, voice=used_voice, language=cfg.tts.language, speed=cfg.tts.speed
        )
        return {
            "ok": True,
            "tool": tool,
            "persona": used_persona,
            "voice": used_voice,
            "speak_length": len(speakable),
            "urgent": urgent,
        }
    except Exception as exc:  # noqa: BLE001 — best-effort speech
        log.warning("TTS speak failed for tool=%s: %s", tool, exc)
        return {"ok": False, "reason": str(exc)}


def process_output_sync(**kwargs: Any) -> dict[str, Any]:
    """Synchronous helper for legacy callers; thin wrapper over :func:`process_output`."""
    return asyncio.run(process_output(**kwargs))
