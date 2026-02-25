"""HTTP client for the TTS server — used by hooks and CLI."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:5959"


class TTSClient:
    """Async client that talks to the claudible TTS server."""

    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def speak(
        self,
        text: str,
        voice: str | None = None,
        language: str = "en",
        speed: float = 1.0,
    ) -> bool:
        """Send text to the TTS server for synthesis and playback.

        Returns True if the server accepted the request.
        """
        payload: dict = {"text": text}
        if voice:
            payload["voice"] = voice
        if language != "en":
            payload["language"] = language
        if speed != 1.0:
            payload["speed"] = speed

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/speak", json=payload)
            if resp.status_code == 200:
                return True
            log.error("TTS server returned %d: %s", resp.status_code, resp.text)
            return False

    async def health(self) -> bool:
        """Check if the TTS server is running."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except httpx.ConnectError:
            return False

    def speak_sync(
        self,
        text: str,
        voice: str | None = None,
        language: str = "en",
        speed: float = 1.0,
    ) -> bool:
        """Synchronous version of speak() for use in hooks."""
        payload: dict = {"text": text}
        if voice:
            payload["voice"] = voice
        if language != "en":
            payload["language"] = language
        if speed != 1.0:
            payload["speed"] = speed

        try:
            resp = httpx.post(
                f"{self.base_url}/speak", json=payload, timeout=self.timeout
            )
            return resp.status_code == 200
        except httpx.ConnectError:
            log.warning("TTS server not reachable at %s", self.base_url)
            return False
