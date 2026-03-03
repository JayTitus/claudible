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
    trigger_word: str = ""
    trigger_mode: str = "always"  # "always" or "ptt"


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


def _check_missing_system_deps() -> list[str]:
    """Check for missing system tools needed by claudible."""
    import shutil

    checks = {
        "cmake": "cmake",
        "make": "build-essential",
        "git": "git",
        "nerd-dictation": "nerd-dictation (see README)",
    }
    missing = []
    for tool, pkg in checks.items():
        if not shutil.which(tool):
            missing.append(pkg)
    return missing


@router.get("/status")
async def get_status():
    from claudible.tts.server import engine

    voices = list_voices()
    missing_deps = _check_missing_system_deps()
    return {
        "model_loaded": engine.is_loaded if engine else False,
        "hook_installed": hook_is_installed(),
        "voice_count": len(voices),
        "input_group": _in_input_group(),
        "rnnoise_installed": is_rnnoise_installed(),
        "rnnoise_active": is_rnnoise_active(),
        "missing_deps": missing_deps,
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

    test_text = (
        f"Hello, this is the {name} voice for claudible. "
        "The quick brown fox jumps over the lazy dog. "
        "All systems are nominal and ready for your command."
    )

    audio, sr = await asyncio.to_thread(
        engine.synthesize,
        test_text,
        voice.wav_file,
        config.tts.language,
        config.tts.speed,
    )
    await _playback_queue.put((audio, sr))
    return {"ok": True}


# ── Personas ────────────────────────────────────────────────────────────────


@router.get("/personas")
async def personas_list():
    from claudible.data.bundled_voices import PERSONA_VOICES

    cfg = Config.load()
    result = []
    for name in list_personas():
        voice = cfg.rephrase.persona_voices.get(name) or PERSONA_VOICES.get(name, "")
        result.append({
            "name": name,
            "custom": is_custom(name),
            "prompt": get_persona_prompt(name),
            "trigger_word": cfg.rephrase.trigger_words.get(name, ""),
            "trigger_mode": cfg.rephrase.trigger_modes.get(name, "always"),
            "voice": voice,
        })
    return result


@router.put("/personas/{name}")
async def persona_put(name: str, body: PersonaBody):
    persona_dir = Path.home() / ".config" / "claudible" / "personas"
    persona_dir.mkdir(parents=True, exist_ok=True)
    dest = persona_dir / f"{name}.txt"
    dest.write_text(body.prompt, encoding="utf-8")
    # Save trigger word + mode to config
    cfg = Config.load()
    if body.trigger_word.strip():
        cfg.rephrase.trigger_words[name] = body.trigger_word.strip()
    else:
        cfg.rephrase.trigger_words.pop(name, None)
    if body.trigger_mode != "always":
        cfg.rephrase.trigger_modes[name] = body.trigger_mode
    else:
        cfg.rephrase.trigger_modes.pop(name, None)
    cfg.save()
    return {"ok": True, "name": name}


class TriggerWordBody(BaseModel):
    trigger_word: str = ""
    trigger_mode: str = "always"


@router.patch("/personas/{name}/trigger")
async def persona_trigger(name: str, body: TriggerWordBody):
    cfg = Config.load()
    if body.trigger_word.strip():
        cfg.rephrase.trigger_words[name] = body.trigger_word.strip()
    else:
        cfg.rephrase.trigger_words.pop(name, None)
    if body.trigger_mode != "always":
        cfg.rephrase.trigger_modes[name] = body.trigger_mode
    else:
        cfg.rephrase.trigger_modes.pop(name, None)
    cfg.save()
    return {"ok": True}


class PersonaActivateBody(BaseModel):
    voice: str = ""


@router.post("/personas/{name}/activate")
async def persona_activate(name: str, body: PersonaActivateBody):
    """Set this persona as active and switch voice."""
    from claudible.data.bundled_voices import PERSONA_VOICES

    cfg = Config.load()
    cfg.rephrase.persona = name
    # Use provided voice, or saved persona voice, or default mapping
    voice = (
        body.voice
        or cfg.rephrase.persona_voices.get(name)
        or PERSONA_VOICES.get(name)
    )
    if voice:
        cfg.tts.voice = voice
        cfg.rephrase.persona_voices[name] = voice
    cfg.save()
    return {"ok": True, "voice": voice or cfg.tts.voice}


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


@router.post("/noise/install")
async def noise_install():
    import asyncio
    import shutil

    from claudible.stt.noise import install_rnnoise, is_rnnoise_installed

    if is_rnnoise_installed():
        return {"ok": True, "message": "Already installed"}

    # Check build deps before attempting
    missing = [t for t in ("cmake", "make", "git") if not shutil.which(t)]
    if missing:
        raise HTTPException(
            400,
            f"Missing build tools: {', '.join(missing)}. "
            f"Install with: sudo apt install cmake build-essential git",
        )

    ok = await asyncio.to_thread(install_rnnoise, auto_yes=True)
    if ok:
        return {"ok": True, "message": "RNNoise installed"}
    raise HTTPException(500, "RNNoise build failed — check server logs")


# ── VOSK models ────────────────────────────────────────────────────────────


@router.get("/vosk-models")
async def vosk_models():
    from claudible.setup.checks import VOSK_MODELS

    vosk_dir = Path.home() / ".local" / "share" / "vosk"
    result = []
    for m in VOSK_MODELS:
        installed = (vosk_dir / m["name"]).is_dir()
        result.append({
            "name": m["name"],
            "label": m["label"],
            "size": m["size"],
            "wer": m["wer"],
            "installed": installed,
        })
    return result


# ── VOSK model download ───────────────────────────────────────────────────


@router.post("/vosk-models/{name}/download")
async def vosk_model_download(name: str):
    import asyncio

    from claudible.setup.checks import VOSK_MODELS, download_vosk_model

    if not any(m["name"] == name for m in VOSK_MODELS):
        raise HTTPException(404, f"Unknown VOSK model: {name}")

    try:
        msg = await asyncio.to_thread(download_vosk_model, name)
        return {"ok": True, "message": msg}
    except (ValueError, RuntimeError) as e:
        raise HTTPException(500, str(e))


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
