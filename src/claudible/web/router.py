"""API routes for the claudible web config UI."""

from __future__ import annotations

import grp
import logging
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from claudible.config import Config
from claudible.hooks.installer import is_installed as hook_is_installed
from claudible.rephrase.ollama import list_models, rephrase
from claudible.rephrase.personas import (
    get_persona_prompt,
    is_custom,
    list_personas,
)
from claudible.stt.noise import (
    disable_rnnoise,
    enable_rnnoise,
    is_rnnoise_active,
    is_rnnoise_installed,
)
from claudible.tts.voices import get_voice_info, list_voices

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── Request/Response models ─────────────────────────────────────────────────


class ConfigPatch(BaseModel):
    tts: dict | None = None
    stt: dict | None = None
    rephrase: dict | None = None
    dictation: dict | None = None


class PersonaBody(BaseModel):
    prompt: str


class RephraseTestBody(BaseModel):
    text: str
    persona: str | None = None


# ── Config ──────────────────────────────────────────────────────────────────


@router.get("/config")
async def get_config():
    cfg = Config.load()
    return cfg.model_dump()


@router.patch("/config/{section}")
async def patch_config(section: str, body: dict):
    if section not in ("tts", "stt", "rephrase", "dictation"):
        raise HTTPException(400, f"Unknown config section: {section}")
    cfg = Config.load()
    sub = getattr(cfg, section)
    for key, value in body.items():
        if hasattr(sub, key):
            setattr(sub, key, value)
    cfg.save()
    return {"ok": True}


# ── Status ──────────────────────────────────────────────────────────────────


def _in_input_group() -> bool:
    try:
        gid = grp.getgrnam("input").gr_gid
        return gid in os.getgroups()
    except (KeyError, OSError):
        return False


@router.get("/status")
async def get_status():
    from claudible.tts.server import engine

    voices = list_voices()
    return {
        "model_loaded": engine.is_loaded if engine else False,
        "hook_installed": hook_is_installed(),
        "voice_count": len(voices),
        "input_group": _in_input_group(),
        "rnnoise_installed": is_rnnoise_installed(),
        "rnnoise_active": is_rnnoise_active(),
    }


# ── Voices ──────────────────────────────────────────────────────────────────


@router.get("/voices")
async def voices():
    result = []
    for v in list_voices():
        try:
            info = get_voice_info(v.name)
            result.append(info)
        except Exception:
            result.append({"name": v.name, "path": str(v.path), "error": True})
    return result


@router.post("/voices/{name}/test")
async def voice_test(name: str):
    from claudible.tts.server import _playback_queue, config, engine

    if not engine or not engine.is_loaded:
        raise HTTPException(503, "TTS engine not loaded")

    from claudible.tts.voices import get_voice

    try:
        voice = get_voice(name)
    except FileNotFoundError:
        raise HTTPException(404, f"Voice '{name}' not found")

    import asyncio

    audio, sr = await asyncio.to_thread(
        engine.synthesize,
        "Hello, this is a voice test from claudible.",
        voice.wav_file,
        config.tts.language,
        config.tts.speed,
    )
    await _playback_queue.put((audio, sr))
    return {"ok": True}


# ── Personas ────────────────────────────────────────────────────────────────


@router.get("/personas")
async def personas_list():
    result = []
    for name in list_personas():
        result.append({
            "name": name,
            "custom": is_custom(name),
            "prompt": get_persona_prompt(name),
        })
    return result


@router.put("/personas/{name}")
async def persona_put(name: str, body: PersonaBody):
    persona_dir = Path.home() / ".config" / "claudible" / "personas"
    persona_dir.mkdir(parents=True, exist_ok=True)
    dest = persona_dir / f"{name}.txt"
    dest.write_text(body.prompt, encoding="utf-8")
    return {"ok": True, "name": name}


@router.delete("/personas/{name}")
async def persona_delete(name: str):
    dest = Path.home() / ".config" / "claudible" / "personas" / f"{name}.txt"
    if not dest.exists():
        raise HTTPException(404, f"Custom persona '{name}' not found")
    dest.unlink()
    return {"ok": True}


# ── Models ──────────────────────────────────────────────────────────────────


@router.get("/models")
async def models():
    cfg = Config.load()
    result = await list_models(cfg)
    return [{"id": m.get("id", "unknown")} for m in result]


# ── Rephrase test ───────────────────────────────────────────────────────────


@router.post("/rephrase/test")
async def rephrase_test(body: RephraseTestBody):
    cfg = Config.load()
    # Temporarily enable rephrase and optionally override persona
    cfg.rephrase.enabled = True
    if body.persona:
        cfg.rephrase.persona = body.persona
    result = await rephrase(body.text, config=cfg)
    return {"result": result}


# ── Noise suppression ──────────────────────────────────────────────────────


@router.get("/noise")
async def noise_status():
    return {
        "installed": is_rnnoise_installed(),
        "active": is_rnnoise_active(),
    }


@router.post("/noise/enable")
async def noise_enable():
    ok = enable_rnnoise()
    return {"ok": ok}


@router.post("/noise/disable")
async def noise_disable():
    ok = disable_rnnoise()
    return {"ok": ok}


# ── Logs ────────────────────────────────────────────────────────────────────


@router.get("/logs")
async def logs(lines: int = 200):
    lines = min(lines, 2000)
    try:
        result = subprocess.run(
            ["journalctl", "--user", "-u", "claudible", "-n", str(lines),
             "--no-hostname", "--no-pager"],
            capture_output=True, text=True, timeout=5,
        )
        return {"logs": result.stdout}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"logs": "(journalctl not available)"}
