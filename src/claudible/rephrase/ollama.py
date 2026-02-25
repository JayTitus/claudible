"""Personality rephrasing via Ollama — transforms Claude output before TTS."""

from __future__ import annotations

import logging

import httpx

from claudible.config import Config
from claudible.rephrase.personas import get_persona_prompt

log = logging.getLogger(__name__)


async def rephrase(text: str, config: Config | None = None) -> str:
    """Rephrase text through Ollama with the configured persona.

    Returns the original text if rephrasing is disabled or fails.
    """
    cfg = config or Config.load()
    if not cfg.rephrase.enabled:
        return text

    system_prompt = get_persona_prompt(cfg.rephrase.persona)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{cfg.rephrase.ollama_url}/api/generate",
                json={
                    "model": cfg.rephrase.model,
                    "system": system_prompt,
                    "prompt": text,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 512},
                },
            )
            resp.raise_for_status()
            result = resp.json().get("response", "").strip()
            if result:
                return result
    except Exception:
        log.warning("Rephrase failed, using original text", exc_info=True)

    return text
