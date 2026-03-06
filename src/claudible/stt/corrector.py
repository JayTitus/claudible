"""STT correction — uses a small LLM to fix VOSK transcription errors."""

from __future__ import annotations

import logging
import time

import httpx

from claudible.config import Config
from claudible.stt.accuracy import log_correction

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a speech transcription corrector. "
    "Fix obvious transcription errors: wrong word boundaries, phonetic "
    "substitutions, missing punctuation. Do NOT change meaning or add words. "
    "Return ONLY the corrected text, nothing else."
)


def _resolve_api_url(cfg: Config) -> str:
    """Resolve the correction API URL from config."""
    if cfg.correction.api_url:
        return cfg.correction.api_url.rstrip("/")
    # Fall back to container port, then default Ollama
    if cfg.container.managed:
        return f"http://127.0.0.1:{cfg.container.port}/v1"
    return cfg.rephrase.api_url.rstrip("/")


async def correct_text(raw: str, config: Config | None = None) -> str:
    """Correct transcription errors using a small LLM.

    Returns the corrected text, or the original on failure/timeout.
    """
    cfg = config or Config.load()
    if not cfg.correction.enabled:
        return raw

    api_url = _resolve_api_url(cfg)
    timeout_s = cfg.correction.timeout_ms / 1000.0
    model = cfg.correction.model

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": raw},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 256,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                corrected = choices[0].get("message", {}).get("content", "").strip()
                if corrected:
                    latency_ms = (time.monotonic() - start) * 1000
                    was_changed = corrected.lower() != raw.lower()
                    if cfg.correction.log_enabled:
                        log_correction(raw, corrected, latency_ms, model, was_changed)
                    if was_changed:
                        log.info("Corrected: %r → %r (%.0fms)", raw, corrected, latency_ms)
                    return corrected
    except Exception:
        log.debug("STT correction failed, using raw text", exc_info=True)

    # Log fallback too
    latency_ms = (time.monotonic() - start) * 1000
    if cfg.correction.log_enabled:
        log_correction(raw, raw, latency_ms, model, was_changed=False)
    return raw
