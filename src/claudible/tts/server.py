"""FastAPI TTS server — persistent daemon that handles synthesis requests."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from claudible.config import Config
from claudible.tts.audio import play_audio
from claudible.tts.engine import TTSEngine
from claudible.tts.voices import get_voice, list_voices

log = logging.getLogger(__name__)

engine: TTSEngine | None = None
config: Config | None = None
_playback_queue: asyncio.Queue | None = None


class SpeakRequest(BaseModel):
    text: str
    voice: str | None = None
    language: str = "en"
    speed: float = 1.0


class SpeakResponse(BaseModel):
    ok: bool
    message: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, config, _playback_queue
    config = Config.load()
    engine = TTSEngine(model_name=config.tts.model)
    engine.load()
    _playback_queue = asyncio.Queue()
    worker = asyncio.create_task(_playback_worker())
    yield
    worker.cancel()


app = FastAPI(title="Claudible TTS", lifespan=lifespan)


async def _playback_worker():
    """Process audio playback requests sequentially to avoid overlapping speech."""
    while True:
        audio, sr = await _playback_queue.get()
        await asyncio.to_thread(play_audio, audio, sr)
        _playback_queue.task_done()


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": engine.is_loaded if engine else False}


@app.get("/voices")
async def voices_list():
    return {"voices": [v.name for v in list_voices()]}


@app.post("/speak", response_model=SpeakResponse)
async def speak(req: SpeakRequest):
    if not engine or not engine.is_loaded:
        raise HTTPException(503, "TTS engine not loaded")

    voice_name = req.voice or config.tts.voice
    try:
        voice = get_voice(voice_name)
    except FileNotFoundError:
        raise HTTPException(404, f"Voice '{voice_name}' not found")

    text = req.text.strip()
    if not text:
        return SpeakResponse(ok=True, message="empty text, nothing to speak")

    # Synthesize in a thread to avoid blocking the event loop
    audio, sr = await asyncio.to_thread(
        engine.synthesize,
        text,
        voice.wav_file,
        req.language,
        req.speed,
    )

    # Queue for sequential playback
    await _playback_queue.put((audio, sr))
    return SpeakResponse(ok=True, message=f"queued {len(text)} chars")


def run_server(host: str = "127.0.0.1", port: int = 5959):
    """Run the TTS server (called from CLI)."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
