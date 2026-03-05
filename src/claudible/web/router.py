"""API routes for the claudible web config UI."""

from __future__ import annotations

import grp
import logging
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from claudible.config import Config
from claudible.hooks.installer import is_installed as hook_is_installed
from claudible.rephrase.ollama import generate_completion_quip, list_models, rephrase
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
from claudible.paths import DATA_DIR, VOICES_DIR, WAKEWORD_STATE, WINDOW_STATE
from claudible.tts.voices import (
    combine_samples,
    get_voice_info,
    list_voices,
    process_voice_sample,
)

STAGING_DIR = DATA_DIR / "voice-staging"

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Callback for restarting the STT key listener when settings change.
# Set by the tray app at startup; called by the save endpoint.
_stt_restart_callback: callable | None = None


def register_stt_restart(callback: callable) -> None:
    """Register a callback to restart the STT key listener."""
    global _stt_restart_callback
    _stt_restart_callback = callback


# ── Request/Response models ─────────────────────────────────────────────────


class ConfigPatch(BaseModel):
    tts: dict | None = None
    stt: dict | None = None
    rephrase: dict | None = None
    dictation: dict | None = None
    completion: dict | None = None
    hook: dict | None = None


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
    if section not in ("tts", "stt", "rephrase", "dictation", "completion", "hook"):
        raise HTTPException(400, f"Unknown config section: {section}")
    cfg = Config.load()
    sub = getattr(cfg, section)
    for key, value in body.items():
        if hasattr(sub, key):
            setattr(sub, key, value)
    cfg.save()

    # Regenerate nerd-dictation callback when dictation/stt settings change
    if section in ("dictation", "stt"):
        try:
            from claudible.stt.callback import generate_callback

            generate_callback(cfg)
        except Exception:
            log.debug("Failed to regenerate callback", exc_info=True)

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


@router.delete("/voices/{name}")
async def voice_delete(name: str):
    """Delete an installed voice and its directory."""
    voice_dir = VOICES_DIR / name
    if not voice_dir.exists():
        raise HTTPException(404, f"Voice '{name}' not found")
    import shutil

    shutil.rmtree(voice_dir)
    return {"ok": True}


# ── Voice Studio ───────────────────────────────────────────────────────


def _get_file_duration(path: Path) -> float:
    """Get audio file duration in seconds."""
    import soundfile as sf

    try:
        info = sf.info(str(path))
        return info.duration
    except Exception:
        return 0.0


@router.post("/voice-studio/upload/{name}")
async def studio_upload(name: str, files: list[UploadFile]):
    """Upload audio file(s) to staging area."""
    if not name.strip():
        raise HTTPException(400, "Voice name is required")

    staging = STAGING_DIR / name
    staging.mkdir(parents=True, exist_ok=True)

    result = []
    for f in files:
        if not f.filename:
            continue
        dest = staging / f.filename
        content = await f.read()
        dest.write_bytes(content)
        duration = _get_file_duration(dest)
        result.append({
            "name": f.filename,
            "duration": round(duration, 1),
            "size_kb": round(len(content) / 1024, 1),
        })

    return result


@router.get("/voice-studio/staging/{name}")
async def studio_staging(name: str):
    """List staged files for a voice name."""
    staging = STAGING_DIR / name
    if not staging.exists():
        return []

    result = []
    for f in sorted(staging.iterdir()):
        if f.is_file():
            duration = _get_file_duration(f)
            result.append({
                "name": f.name,
                "duration": round(duration, 1),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    return result


@router.delete("/voice-studio/staging/{name}/{filename}")
async def studio_staging_delete_file(name: str, filename: str):
    """Remove a single staged file."""
    target = STAGING_DIR / name / filename
    if not target.exists():
        raise HTTPException(404, "Staged file not found")
    target.unlink()
    return {"ok": True}


@router.delete("/voice-studio/staging/{name}")
async def studio_staging_clear(name: str):
    """Clear all staged files for a voice name."""
    staging = STAGING_DIR / name
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    return {"ok": True}


@router.post("/voice-studio/create/{name}")
async def studio_create(name: str):
    """Process staged files into an installed voice."""
    import asyncio

    staging = STAGING_DIR / name
    if not staging.exists():
        raise HTTPException(400, "No staged files found")

    staged = sorted(f for f in staging.iterdir() if f.is_file())
    if not staged:
        raise HTTPException(400, "No staged files found")

    try:
        if len(staged) == 1:
            voice = await asyncio.to_thread(process_voice_sample, staged[0], name)
        else:
            voice = await asyncio.to_thread(
                combine_samples, staged, name, target_duration=15.0
            )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Clean up staging
    import shutil

    shutil.rmtree(staging)

    # Return info about the created voice
    try:
        info = get_voice_info(name)
    except Exception:
        info = {"name": name, "path": str(voice.path)}

    return info


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


# ── Completion ─────────────────────────────────────────────────────────────


@router.post("/completion/test")
async def completion_test():
    """Generate and return a completion quip without speaking."""
    cfg = Config.load()
    cfg.rephrase.enabled = True  # force enabled for test
    quip = await generate_completion_quip(cfg)
    if quip:
        prefix = cfg.completion.persona_prefix.strip()
        result = f"{prefix} {quip}".strip() if prefix else quip
    else:
        result = cfg.completion.simple_phrase
    return {"result": result}


# ── Hook / IVR test ───────────────────────────────────────────────────────


class OptionTestBody(BaseModel):
    text: str


@router.post("/hook/test-options")
async def hook_test_options(body: OptionTestBody):
    """Test option detection and IVR formatting on sample text."""
    from claudible.hooks.filter import extract_options, extract_speakable
    from claudible.hooks.stop_hook import _format_ivr

    options = extract_options(body.text)
    speakable = extract_speakable(body.text)

    ivr_text = None
    if options:
        ivr_text = _format_ivr(speakable or "", options)

    return {
        "options": [{"num": n, "desc": d} for n, d in options] if options else [],
        "speakable": speakable,
        "ivr_text": ivr_text,
    }


# ── Wake word state ───────────────────────────────────────────────────────


@router.get("/wakeword/state")
async def wakeword_state():
    """Read the current wake word state from the state file."""
    import json

    try:
        with open(WAKEWORD_STATE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"state": "sleeping", "activated_at": 0.0}


# ── STT restart ───────────────────────────────────────────────────────────


@router.post("/stt/restart")
async def stt_restart():
    """Restart the STT key listener with current config."""
    if _stt_restart_callback:
        try:
            _stt_restart_callback()
            return {"ok": True, "message": "STT restarted"}
        except Exception as e:
            raise HTTPException(500, f"Restart failed: {e}")
    return {"ok": True, "message": "No listener registered (not running via tray)"}


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


# ── Window lock ────────────────────────────────────────────────────────────


class WindowRegisterBody(BaseModel):
    slot: str = "1"
    window_id: int | None = None


@router.get("/windows")
async def windows_list():
    """List registered windows with alive status."""
    from claudible.stt.windows import read_window_state, validate_window

    state = read_window_state()
    windows = state.get("windows", {})
    result = []
    for slot, entry in sorted(windows.items()):
        wid = entry.get("window_id")
        alive = validate_window(wid) if wid else False
        result.append({
            "slot": slot,
            "window_id": wid,
            "title": entry.get("title", ""),
            "pid": entry.get("pid"),
            "process": entry.get("process"),
            "alive": alive,
        })
    return result


@router.get("/windows/watched")
async def windows_watched():
    """Return watched process list and currently detected processes."""
    from claudible.stt.procwatch import scan_proc_for_names

    cfg = Config.load()
    names = cfg.stt.watched_processes
    detected = scan_proc_for_names(names)
    return {
        "watched_processes": names,
        "process_watch_interval": cfg.stt.process_watch_interval,
        "detected": detected,
    }


@router.post("/windows/register")
async def windows_register(body: WindowRegisterBody):
    """Register a window to a slot. Captures active window if no window_id given."""
    from claudible.stt.windows import register_window

    try:
        state = register_window(body.slot, body.window_id)
        entry = state.get("windows", {}).get(body.slot, {})
        return {"ok": True, "slot": body.slot, **entry}
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.delete("/windows/{slot}")
async def windows_unregister(slot: str):
    """Unregister a window slot."""
    from claudible.stt.windows import unregister_window

    unregister_window(slot)
    return {"ok": True}


@router.delete("/windows")
async def windows_clear():
    """Clear all window registrations."""
    from claudible.stt.windows import clear_all_windows

    clear_all_windows()
    return {"ok": True}


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
