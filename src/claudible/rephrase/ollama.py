"""Personality rephrasing via OpenAI-compatible API (Ollama, Open WebUI, etc.)."""

from __future__ import annotations

import logging

import httpx

from claudible.config import Config
from claudible.rephrase.personas import get_persona_prompt

log = logging.getLogger(__name__)


async def rephrase(text: str, config: Config | None = None) -> str:
    """Rephrase text through an OpenAI-compatible chat API with the configured persona.

    Works with Ollama (/v1), Open WebUI, or any OpenAI-compatible endpoint.
    Returns the original text if rephrasing is disabled or fails.
    """
    cfg = config or Config.load()
    if not cfg.rephrase.enabled:
        return text

    system_prompt = get_persona_prompt(cfg.rephrase.persona)
    api_url = cfg.rephrase.api_url.rstrip("/")

    headers = {"Content-Type": "application/json"}
    if cfg.rephrase.api_key:
        headers["Authorization"] = f"Bearer {cfg.rephrase.api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers=headers,
                json={
                    "model": cfg.rephrase.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 512,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                result = choices[0].get("message", {}).get("content", "").strip()
                if result:
                    return result
    except Exception:
        log.warning("Rephrase failed, using original text", exc_info=True)

    return text


async def list_models(config: Config | None = None) -> list[dict]:
    """List available models from the OpenAI-compatible endpoint.

    Returns a list of dicts with at least 'id' key.
    """
    cfg = config or Config.load()
    api_url = cfg.rephrase.api_url.rstrip("/")

    headers = {}
    if cfg.rephrase.api_key:
        headers["Authorization"] = f"Bearer {cfg.rephrase.api_key}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{api_url}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # OpenAI format: {"data": [...]}
            models = data.get("data", [])
            if isinstance(models, list):
                return models
    except Exception:
        log.debug("Failed to list models", exc_info=True)

    return []
