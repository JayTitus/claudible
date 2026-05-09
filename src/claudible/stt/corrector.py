"""STT correction — uses a small LLM to fix VOSK transcription errors."""

from __future__ import annotations

import logging
import time

import httpx

from claudible.config import Config
from claudible.stt.accuracy import log_correction

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You fix speech-to-text transcription errors. "
    "Input: raw STT output. Output: corrected text only. "
    "Rules: fix word boundaries, homophones, and phonetic errors. "
    "Do NOT add words, explain, ask questions, or respond conversationally. "
    "Do NOT change meaning. Keep it the same length. "
    "If the text looks fine, repeat it exactly."
)


# Phrases that indicate the model went conversational instead of correcting
_BAD_PATTERNS = (
    "here to help", "i can help", "what's the", "what is the",
    "could you", "can you", "please provide", "i think",
    "it seems", "it looks", "sure,", "sure!", "of course",
    "i'd be happy", "let me", "here's the", "here is the",
)


def _is_bad_correction(raw: str, corrected: str) -> bool:
    """Check if the correction looks like conversational LLM output."""
    raw_len = len(raw)
    corrected_len = len(corrected)

    # Reject if output is more than 2x the input length
    if corrected_len > max(raw_len * 2, raw_len + 40):
        return True

    # Reject if it contains conversational patterns
    lower = corrected.lower()
    for pattern in _BAD_PATTERNS:
        if pattern in lower and pattern not in raw.lower():
            return True

    # Reject if it contains multiple sentences when input was one
    if raw.count(".") <= 1 and corrected.count(".") >= 3:
        return True

    return False


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
                    "max_tokens": max(len(raw.split()) * 3, 30),
                    "stream": False,
                },
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                corrected = choices[0].get("message", {}).get("content", "").strip()
                if corrected:
                    # Guardrail: reject if model went conversational
                    if _is_bad_correction(raw, corrected):
                        log.warning(
                            "Rejected correction (bad output): %r → %r", raw, corrected,
                        )
                        corrected = raw
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
