"""CLI entry point for claudible."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from claudible import __version__


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


@click.group(invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.version_option(__version__)
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Claudible — Voice interface for Claude Code."""
    _setup_logging(verbose)
    if ctx.invoked_subcommand is None:
        _status()


def _status() -> None:
    """Show claudible status overview."""
    from claudible.config import Config
    from claudible.hooks.installer import is_installed
    from claudible.lifecycle import is_running, read_pid
    from claudible.tts.voices import list_voices

    cfg = Config.load()
    voices = list_voices()
    hook_ok = is_installed()
    pid = read_pid()
    running = is_running()

    click.echo(f"claudible v{__version__}")
    click.echo(f"  TTS server:  {cfg.tts.host}:{cfg.tts.port}")
    click.echo(f"  TTS model:   {cfg.tts.model}")
    click.echo(f"  Voice:       {cfg.tts.voice}")
    click.echo(f"  Voices:      {len(voices)} installed")
    click.echo(f"  Rephrase:    {'on' if cfg.rephrase.enabled else 'off'}")
    click.echo(f"  Hook:        {'installed' if hook_ok else 'not installed'}")

    if running:
        click.echo(f"  Process:     running (PID {pid})")
    else:
        click.echo("  Process:     not running")

    # Quick health check
    from claudible.tts.client import TTSClient

    client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")
    healthy = asyncio.run(client.health())
    click.echo(f"  Server:      {'running' if healthy else 'not running'}")


@main.command()
def start() -> None:
    """Start the TTS server + system tray.

    Prefer `systemctl --user start claudible` for background operation.
    """
    import os
    import threading

    from claudible.config import Config
    from claudible.lifecycle import is_running, read_pid, write_pid
    from claudible.paths import find_cudnn_lib

    # Ensure cuDNN is discoverable (systemd service sets this too, but
    # direct CLI invocation needs it as well).
    cudnn_path = find_cudnn_lib()
    if cudnn_path:
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        if cudnn_path not in existing:
            os.environ["LD_LIBRARY_PATH"] = f"{cudnn_path}:{existing}" if existing else cudnn_path

    if is_running():
        pid = read_pid()
        click.echo(f"Claudible is already running (PID {pid}).")
        sys.exit(0)

    write_pid()
    cfg = Config.load()

    # Ensure nerd-dictation callback is current (Linux only — macOS uses direct VOSK)
    from claudible.platform import detect_platform

    if detect_platform() == "linux":
        try:
            from claudible.stt.callback import generate_callback

            generate_callback(cfg)
        except Exception:
            pass

    # Check if server is already running (e.g. started externally)
    from claudible.tts.client import TTSClient

    client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")
    already_running = asyncio.run(client.health())

    if already_running:
        click.echo(f"TTS server already running on {cfg.tts.host}:{cfg.tts.port}")
    else:
        click.echo(f"Starting TTS server on {cfg.tts.host}:{cfg.tts.port} ...")

        def _run_server() -> None:
            import uvicorn

            from claudible.tts.server import app

            uvicorn.run(app, host=cfg.tts.host, port=cfg.tts.port, log_level="warning")

        t = threading.Thread(target=_run_server, daemon=True)
        t.start()

    # Pre-generate icons BEFORE pystray import to avoid Pillow/GTK conflict on KDE
    try:
        from claudible.gui.icons import ensure_icons

        ensure_icons()
    except ImportError:
        pass

    try:
        from claudible.gui.tray import TrayApp
    except ImportError:
        click.echo("GUI deps not installed. Install with: pip install claudible[gui]", err=True)
        sys.exit(1)

    click.echo("Launching tray icon (foreground — Ctrl+C to stop)...")
    click.echo("  Tip: use `systemctl --user start claudible` for background mode")
    app = TrayApp()
    app.run()


@main.command()
def stop() -> None:
    """Stop the running claudible process.

    Prefer `systemctl --user stop claudible` for systemd-managed instances.
    """
    from claudible.config import Config
    from claudible.lifecycle import is_running, stop_running
    from claudible.tts.client import TTSClient

    if not is_running():
        click.echo("Claudible is not running.")
        sys.exit(0)

    stopped = stop_running()
    if stopped:
        click.echo("Claudible stopped.")
    else:
        # Fallback: try /shutdown endpoint
        cfg = Config.load()
        client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")
        try:
            import httpx

            httpx.post(f"http://{cfg.tts.host}:{cfg.tts.port}/shutdown", timeout=5)
            click.echo("Claudible stopped via server shutdown.")
        except Exception:
            click.echo("Failed to stop claudible.", err=True)
            sys.exit(1)


@main.command()
@click.pass_context
def restart(ctx: click.Context) -> None:
    """Restart claudible. Uses systemd/launchd if available, otherwise background process."""
    import subprocess
    import time

    from claudible.lifecycle import is_running
    from claudible.platform import get_daemon_backend

    if is_running():
        ctx.invoke(stop)
        time.sleep(1)

    # Prefer OS service manager if available and enabled
    daemon = get_daemon_backend()
    if daemon and daemon.is_service_enabled():
        if daemon.start_service():
            click.echo("Claudible started via service manager.")
            return

    # Fallback: launch in background
    subprocess.Popen(
        [sys.executable, "-m", "claudible.cli", "start"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    click.echo("Claudible restarted in background.")


@main.command()
def ptt() -> None:
    """Start the push-to-talk listener."""
    from claudible.config import Config
    from claudible.platform import get_keyboard_backend

    kb = get_keyboard_backend()
    if kb is None:
        click.echo("Push-to-talk not available (missing platform deps).", err=True)
        click.echo("Install with: pip install claudible[linux] or claudible[macos]", err=True)
        sys.exit(1)

    cfg = Config.load()
    kb.run_ptt(cfg)


@main.command()
@click.argument("text")
@click.option("--voice", "-V", default=None, help="Voice to use")
def speak(text: str, voice: str | None) -> None:
    """Send text to the TTS server for speech."""
    from claudible.config import Config
    from claudible.tts.client import TTSClient

    cfg = Config.load()
    client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")
    ok = asyncio.run(client.speak(text, voice=voice or cfg.tts.voice))
    if not ok:
        click.echo("Failed to send to TTS server. Is it running?", err=True)
        sys.exit(1)


@main.group()
def voices() -> None:
    """Manage voice profiles."""


@voices.command("list")
def voices_list() -> None:
    """List installed voices."""
    from claudible.tts.voices import list_voices

    for v in list_voices():
        click.echo(f"  {v.name}  ({v.wav_file.name})")
    if not list_voices():
        click.echo("  No voices installed. Use 'claudible voices add' to add one.")


@voices.command("add")
@click.argument("name")
@click.argument("wav_file", type=click.Path(exists=True, path_type=Path))
def voices_add(name: str, wav_file: Path) -> None:
    """Add a voice from a WAV file (validates and resamples to 22050 Hz mono)."""
    from claudible.tts.voices import process_voice_sample, validate_voice_sample

    issues = validate_voice_sample(wav_file)
    if issues:
        for issue in issues:
            if issue.startswith("ERROR:"):
                click.echo(click.style(issue, fg="red"))
            else:
                click.echo(click.style(issue, fg="yellow"))
        errors = [i for i in issues if i.startswith("ERROR:")]
        if errors:
            sys.exit(1)
        if not click.confirm("Continue with these warnings?", default=True):
            sys.exit(0)

    voice = process_voice_sample(wav_file, name)
    click.echo(f"Voice '{voice.name}' added at {voice.path}")


@voices.command("test")
@click.argument("name")
def voices_test(name: str) -> None:
    """Test a voice by speaking a sample phrase."""
    from claudible.config import Config
    from claudible.tts.client import TTSClient

    cfg = Config.load()
    client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")
    ok = asyncio.run(client.speak("Hello, this is a voice test from claudible.", voice=name))
    if not ok:
        click.echo("Failed. Is the TTS server running?", err=True)
        sys.exit(1)


@voices.command("info")
@click.argument("name")
def voices_info(name: str) -> None:
    """Show details about a voice sample."""
    from claudible.tts.voices import get_voice_info

    info = get_voice_info(name)
    click.echo(f"  Name:        {info['name']}")
    click.echo(f"  File:        {info['path']}")
    click.echo(f"  Duration:    {info['duration']}s")
    click.echo(f"  Sample rate: {info['sample_rate']} Hz")
    click.echo(f"  Channels:    {info['channels']}")
    click.echo(f"  Size:        {info['file_size_kb']} KB")


@voices.command("combine")
@click.argument("name")
@click.argument("sources", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--duration", "-d", default=15.0, help="Target duration in seconds (default: 15)")
@click.option("--gap", "-g", default=0.5, help="Silence gap between clips in seconds (default: 0.5)")
def voices_combine(name: str, sources: tuple[Path, ...], duration: float, gap: float) -> None:
    """Combine multiple short audio clips into one XTTS-ready voice sample.

    Picks the longest clips first until target duration is reached.
    Accepts WAV, MP3, FLAC, OGG files.

    Example: claudible voices combine my-voice clip1.wav clip2.mp3 clip3.wav
    """
    from claudible.tts.voices import combine_samples, get_voice_info

    click.echo(f"Combining {len(sources)} clips into voice '{name}' (target {duration}s)...")
    voice = combine_samples(list(sources), name, target_duration=duration, silence_gap=gap)
    info = get_voice_info(name)
    click.echo(f"  Created: {voice.path}/sample.wav")
    click.echo(f"  Duration: {info['duration']}s | {info['file_size_kb']} KB")
    click.echo(f"\nTest with: claudible voices test {name}")


@voices.command("record")
@click.argument("name")
@click.option("--duration", "-d", default=10, help="Recording duration in seconds")
def voices_record(name: str, duration: int) -> None:
    """Record a voice sample from your microphone."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    from claudible.paths import VOICES_DIR, ensure_dirs

    ensure_dirs()
    voice_dir = VOICES_DIR / name
    voice_dir.mkdir(parents=True, exist_ok=True)
    wav_path = voice_dir / "sample.wav"

    click.echo(f"Recording {duration}s of audio. Speak clearly...")
    click.echo("Press Ctrl+C to stop early.")

    try:
        audio = sd.rec(int(duration * 22050), samplerate=22050, channels=1, dtype="float32")
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
        audio = sd.get_stream().read(sd.get_stream().read_available)[0]

    audio = np.squeeze(audio)
    sf.write(str(wav_path), audio, 22050)
    click.echo(f"Voice '{name}' saved to {wav_path}")


@main.group()
def personas() -> None:
    """Manage rephrase personas."""


@personas.command("list")
def personas_list() -> None:
    """List available personas."""
    from claudible.rephrase.personas import is_custom, list_personas

    for name in list_personas():
        tag = " (custom)" if is_custom(name) else ""
        click.echo(f"  {name}{tag}")


@personas.command("show")
@click.argument("name")
def personas_show(name: str) -> None:
    """Show the prompt for a persona."""
    from claudible.rephrase.personas import get_persona_prompt

    click.echo(get_persona_prompt(name))


@personas.command("create")
@click.argument("name")
@click.option("--prompt", "-p", default=None, help="The persona system prompt (or omit to open editor)")
def personas_create(name: str, prompt: str | None) -> None:
    """Create a custom persona."""
    persona_dir = Path.home() / ".config" / "claudible" / "personas"
    persona_dir.mkdir(parents=True, exist_ok=True)
    dest = persona_dir / f"{name}.txt"

    if dest.exists():
        if not click.confirm(f"Persona '{name}' already exists. Overwrite?"):
            return

    if prompt is None:
        prompt = click.edit(f"# Write the system prompt for persona '{name}'.\n# This text tells the LLM how to rephrase Claude's output before speaking.\n")
        if not prompt or not prompt.strip():
            click.echo("Aborted — empty prompt.", err=True)
            return
        # Strip comment lines
        lines = [l for l in prompt.splitlines() if not l.strip().startswith("#")]
        prompt = "\n".join(lines).strip()

    dest.write_text(prompt, encoding="utf-8")
    click.echo(f"Persona '{name}' saved to {dest}")
    click.echo(f"Activate with: claudible config → rephrase.persona = \"{name}\"")


@personas.command("delete")
@click.argument("name")
def personas_delete(name: str) -> None:
    """Delete a custom persona."""
    dest = Path.home() / ".config" / "claudible" / "personas" / f"{name}.txt"
    if not dest.exists():
        click.echo(f"Custom persona '{name}' not found.", err=True)
        sys.exit(1)
    dest.unlink()
    click.echo(f"Persona '{name}' deleted.")


@main.group()
def windows() -> None:
    """Manage window lock slots for dictation."""


@windows.command("list")
def windows_list() -> None:
    """Show registered window slots with alive status."""
    from claudible.platform import get_window_backend

    wb = get_window_backend()
    if wb is None:
        # Fallback to direct import for backwards compat
        from claudible.stt.windows import read_window_state, validate_window
        state = read_window_state()
        _validate = validate_window
    else:
        state = wb.read_window_state()
        _validate = wb.validate_window

    wins = state.get("windows", {})
    if not wins:
        click.echo("  No windows registered.")
        return
    for slot, entry in sorted(wins.items()):
        wid = entry.get("window_id")
        title = entry.get("title", "")
        pid = entry.get("pid")
        process = entry.get("process")
        alive = _validate(wid) if wid else False
        status = click.style("alive", fg="green") if alive else click.style("gone", fg="red")
        if process:
            source = f"{process} (PID {pid})"
        else:
            source = "(manual)"
        click.echo(f"  Slot {slot}: {wid} ({title}) [{status}] {source}")


@windows.command("register")
@click.argument("slot", default="1")
def windows_register(slot: str) -> None:
    """Register the focused window to a slot (default: 1)."""
    from claudible.platform import get_window_backend

    wb = get_window_backend()
    if wb is None:
        click.echo("Window management not available on this platform.", err=True)
        sys.exit(1)

    try:
        state = wb.register_window(slot)
        entry = state.get("windows", {}).get(slot, {})
        click.echo(f"Registered slot {slot}: {entry.get('window_id')} ({entry.get('title', '')})")
    except RuntimeError as e:
        click.echo(f"Failed: {e}", err=True)
        sys.exit(1)


@windows.command("clear")
def windows_clear() -> None:
    """Clear all window registrations."""
    from claudible.platform import get_window_backend

    wb = get_window_backend()
    if wb is not None:
        wb.clear_all_windows()
    else:
        from claudible.stt.windows import clear_all_windows
        clear_all_windows()
    click.echo("All window registrations cleared.")


@main.group()
def container() -> None:
    """Manage the bundled Ollama container."""


@container.command("start")
def container_start() -> None:
    """Start the Ollama container."""
    from claudible.config import Config
    from claudible.container.ollama import _wait_for_ready, start_container

    cfg = Config.load()
    click.echo(f"Starting Ollama container on port {cfg.container.port}...")
    ok = start_container(cfg.container.port, cfg.container.gpu)
    if not ok:
        click.echo("Failed to start container.", err=True)
        sys.exit(1)
    click.echo("Waiting for Ollama to become ready...")
    ready = _wait_for_ready(cfg.container.port, 30.0)
    if ready:
        click.echo("Ollama container is ready.")
    else:
        click.echo("Container started but not yet responding.", err=True)


@container.command("stop")
def container_stop() -> None:
    """Stop the Ollama container."""
    from claudible.container.ollama import stop_container

    ok = stop_container()
    if ok:
        click.echo("Ollama container stopped.")
    else:
        click.echo("Failed to stop container.", err=True)
        sys.exit(1)


@container.command("status")
def container_status_cmd() -> None:
    """Show container status and models."""
    from claudible.config import Config
    from claudible.container.ollama import container_status, health_check, list_models

    cfg = Config.load()
    port = cfg.container.port
    status = container_status()
    click.echo(f"  Container:  {status['status']}")
    click.echo(f"  Port:       {port}")
    click.echo(f"  Managed:    {'yes' if cfg.container.managed else 'no'}")

    if status["running"]:
        healthy = health_check(port)
        click.echo(f"  Healthy:    {'yes' if healthy else 'no'}")
        if healthy:
            models = list_models(port)
            if models:
                click.echo("  Models:")
                for m in models:
                    click.echo(f"    - {m.get('name', '?')}")
            else:
                click.echo("  Models:     (none)")


@container.command("pull")
@click.argument("model")
def container_pull(model: str) -> None:
    """Pull a model into the running container."""
    from claudible.config import Config
    from claudible.container.ollama import pull_model

    cfg = Config.load()
    click.echo(f"Pulling {model}...")
    ok = pull_model(model, cfg.container.port)
    if ok:
        click.echo(f"Model {model} pulled successfully.")
    else:
        click.echo(f"Failed to pull {model}.", err=True)
        sys.exit(1)


@container.command("enable")
def container_enable() -> None:
    """Enable managed container mode, start container, and pull models."""
    from claudible.config import Config
    from claudible.container.ollama import (
        _wait_for_ready,
        ensure_model,
        health_check,
        start_container,
    )

    cfg = Config.load()
    cfg.container.managed = True
    cfg.correction.enabled = True
    cfg.save()

    port = cfg.container.port
    click.echo(f"Managed container enabled on port {port}.")

    if not health_check(port):
        click.echo("Starting Ollama container...")
        ok = start_container(port, cfg.container.gpu)
        if not ok:
            click.echo("Failed to start container.", err=True)
            sys.exit(1)
        click.echo("Waiting for Ollama...")
        if not _wait_for_ready(port, 30.0):
            click.echo("Container not responding.", err=True)
            sys.exit(1)

    click.echo(f"Pulling correction model: {cfg.container.correction_model}")
    ensure_model(cfg.container.correction_model, port)
    click.echo(f"Pulling rephrase model: {cfg.container.rephrase_model}")
    ensure_model(cfg.container.rephrase_model, port)
    click.echo("All models ready. STT correction is now enabled.")


@main.group()
def accuracy() -> None:
    """STT correction accuracy tracking."""


@accuracy.command("report")
def accuracy_report() -> None:
    """Show accuracy statistics."""
    from claudible.stt.accuracy import compute_stats, read_log

    entries = read_log()
    if not entries:
        click.echo("No correction data yet.")
        return
    stats = compute_stats(entries)
    click.echo(f"  Total corrections:  {stats['total']}")
    click.echo(f"  Changed:            {stats['changed']} ({stats['change_rate']}%)")
    click.echo(f"  Avg latency:        {stats['avg_latency_ms']}ms")
    click.echo(f"  P50 latency:        {stats['p50_latency_ms']}ms")
    click.echo(f"  P95 latency:        {stats['p95_latency_ms']}ms")


@accuracy.command("tail")
@click.option("-n", "--count", default=10, help="Number of entries to show")
def accuracy_tail(count: int) -> None:
    """Show recent correction entries."""
    from claudible.stt.accuracy import read_log

    entries = read_log(count)
    if not entries:
        click.echo("No correction data yet.")
        return
    for e in entries:
        changed = "*" if e.was_changed else " "
        click.echo(f"  {changed} {e.raw!r} → {e.corrected!r}  ({e.latency_ms}ms)")


@accuracy.command("clear")
def accuracy_clear() -> None:
    """Clear the accuracy log."""
    from claudible.stt.accuracy import clear_log

    clear_log()
    click.echo("Accuracy log cleared.")


@main.group()
def vad() -> None:
    """Silero VAD voice activity detection."""


@vad.command("test")
@click.argument("wav_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--threshold", type=float, default=None, help="Override config threshold (0..1)")
@click.option("--min-speech-ms", type=int, default=None)
@click.option("--min-silence-ms", type=int, default=None)
@click.option("--save-segments", type=click.Path(file_okay=False), default=None,
              help="Write each detected speech segment to this directory as WAV.")
def vad_test(wav_file: str, threshold: float | None,
             min_speech_ms: int | None, min_silence_ms: int | None,
             save_segments: str | None) -> None:
    """Run VAD on a WAV file and print detected speech segments.

    Useful for tuning the threshold without a microphone — feed in an
    audio file and inspect what gets classified as speech vs noise.
    """
    import soundfile as sf
    from claudible.config import Config
    from claudible.stt.vad import SpeechGate

    cfg = Config.load()
    audio, sr = sf.read(wav_file, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        click.echo(f"Resampling {sr} → 16000 Hz...")
        import numpy as np

        ratio = 16000 / sr
        new_len = int(len(audio) * ratio)
        audio = np.interp(
            np.linspace(0, len(audio) - 1, new_len),
            np.arange(len(audio)),
            audio,
        ).astype("float32")
        sr = 16000

    gate = SpeechGate(
        sample_rate=sr,
        threshold=threshold if threshold is not None else cfg.stt.vad_threshold,
        min_speech_ms=min_speech_ms if min_speech_ms is not None else cfg.stt.vad_min_speech_ms,
        min_silence_ms=min_silence_ms if min_silence_ms is not None else cfg.stt.vad_min_silence_ms,
        speech_pad_ms=cfg.stt.vad_speech_pad_ms,
    )

    events = gate.feed(audio)
    window_ms = gate._vad.window_samples * 1000 / sr  # type: ignore[attr-defined]

    segments: list[tuple[float, float, list]] = []
    cur_start: float | None = None
    cur_audio: list = []
    probs: list[float] = []

    for i, evt in enumerate(events):
        t_ms = i * window_ms
        probs.append(evt.probability)
        if evt.event == "speech_start":
            cur_start = t_ms
            cur_audio = [w for w in evt.pad] + [evt.audio]
        elif evt.event == "speech_end" and cur_start is not None:
            cur_audio.append(evt.audio)
            segments.append((cur_start, t_ms, cur_audio))
            cur_start = None
            cur_audio = []
        elif evt.is_speech and evt.audio is not None:
            cur_audio.append(evt.audio)

    if cur_start is not None:
        segments.append((cur_start, len(events) * window_ms, cur_audio))

    duration_ms = len(events) * window_ms
    speech_ms = sum(e - s for s, e, _ in segments)
    avg_prob = sum(probs) / len(probs) if probs else 0
    click.echo(f"  File:           {wav_file}")
    click.echo(f"  Duration:       {duration_ms / 1000:.2f}s ({len(events)} windows)")
    click.echo(f"  Speech total:   {speech_ms / 1000:.2f}s ({speech_ms / duration_ms * 100:.1f}%)" if duration_ms else "  Speech total:   0s")
    click.echo(f"  Mean p(speech): {avg_prob:.3f}")
    click.echo(f"  Threshold:      {gate.threshold:.2f}")
    click.echo(f"  Segments:       {len(segments)}")
    for i, (s, e, _) in enumerate(segments):
        click.echo(f"    [{i + 1}] {s / 1000:6.2f}s → {e / 1000:6.2f}s  ({(e - s) / 1000:.2f}s)")

    if save_segments and segments:
        import numpy as np
        from pathlib import Path

        out_dir = Path(save_segments)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, (_, _, audio_chunks) in enumerate(segments):
            seg_audio = np.concatenate(audio_chunks)
            out_path = out_dir / f"segment_{i + 1:03d}.wav"
            sf.write(str(out_path), seg_audio, sr, subtype="PCM_16")
        click.echo(f"  Wrote {len(segments)} segment(s) to {out_dir}")


@main.group()
def hooks() -> None:
    """Manage Claude Code hooks."""


@hooks.command("install")
def hooks_install() -> None:
    """Install the Claude Code stop hook."""
    from claudible.hooks.installer import install_hook

    install_hook()
    click.echo("Claude Code stop hook installed.")


@hooks.command("uninstall")
def hooks_uninstall() -> None:
    """Remove the Claude Code stop hook."""
    from claudible.hooks.installer import uninstall_hook

    uninstall_hook()
    click.echo("Claude Code stop hook removed.")


@hooks.command("status")
def hooks_status() -> None:
    """Check if the hook is installed."""
    from claudible.hooks.installer import is_installed

    if is_installed():
        click.echo("Claudible hook is installed.")
    else:
        click.echo("Claudible hook is NOT installed.")


@main.command()
@click.option("--yes", "-y", is_flag=True, help="Non-interactive mode (auto-accept prompts)")
@click.option("--skip-gpu", is_flag=True, help="Skip GPU/CUDA checks")
def install(yes: bool, skip_gpu: bool) -> None:
    """Full interactive setup — checks deps, configures voice, and gets you started."""
    from claudible.setup.wizard import run_wizard

    run_wizard(auto_yes=yes, skip_gpu=skip_gpu)


@main.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--keep-voices", is_flag=True, help="Keep voice samples")
def uninstall(yes: bool, keep_voices: bool) -> None:
    """Remove claudible config, data, hooks, and services.

    Does NOT remove the package itself — run `uv tool uninstall claudible` after.
    """
    import shutil

    from claudible.hooks.installer import is_installed, uninstall_hook
    from claudible.lifecycle import is_running, stop_running
    from claudible.paths import CACHE_DIR, CONFIG_DIR, DATA_DIR, VOICES_DIR
    from claudible.platform import get_daemon_backend

    if not yes:
        click.echo("This will remove:")
        click.echo(f"  Config:   {CONFIG_DIR}")
        if not keep_voices:
            click.echo(f"  Data:     {DATA_DIR}")
        else:
            click.echo(f"  Data:     {DATA_DIR} (keeping voices)")
        click.echo(f"  Cache:    {CACHE_DIR}")
        if is_installed():
            click.echo("  Claude Code hook")
        click.echo()
        if not click.confirm("Proceed?", default=False):
            click.echo("Aborted.")
            return

    # Stop running process
    if is_running():
        click.echo("Stopping claudible...")
        stop_running()

    # Remove systemd/launchd service
    daemon = get_daemon_backend()
    if daemon and daemon.is_service_enabled():
        click.echo("Removing background service...")
        daemon.stop_service()
        # Disable and remove systemd unit file (Linux)
        unit_file = Path.home() / ".config" / "systemd" / "user" / "claudible.service"
        if unit_file.exists():
            import subprocess

            subprocess.run(
                ["systemctl", "--user", "disable", "claudible"],
                capture_output=True,
            )
            unit_file.unlink(missing_ok=True)
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
            )

    # Remove Claude Code hook
    if is_installed():
        click.echo("Removing Claude Code hook...")
        uninstall_hook()

    # Remove cache
    if CACHE_DIR.exists():
        click.echo(f"Removing {CACHE_DIR}")
        shutil.rmtree(CACHE_DIR)

    # Remove data (optionally keep voices)
    if DATA_DIR.exists():
        if keep_voices:
            # Remove everything in DATA_DIR except voices
            for child in DATA_DIR.iterdir():
                if child != VOICES_DIR:
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            click.echo(f"Removed {DATA_DIR} (kept voices)")
        else:
            shutil.rmtree(DATA_DIR)
            click.echo(f"Removed {DATA_DIR}")

    # Remove config
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR)
        click.echo(f"Removed {CONFIG_DIR}")

    click.echo()
    click.echo("Claudible data removed.")

    # Detect install method and show appropriate removal instructions
    import importlib.metadata

    try:
        dist = importlib.metadata.distribution("claudible")
        direct_url = dist.read_text("direct_url.json")
        if direct_url and '"editable"' in direct_url:
            click.echo("Installed as editable dev package — no further removal needed.")
        else:
            click.echo("To remove the package: uv tool uninstall claudible")
    except importlib.metadata.PackageNotFoundError:
        pass


@main.command("config")
def config_cmd() -> None:
    """Open the web config UI in a browser."""
    import webbrowser

    from claudible.config import Config
    from claudible.tts.client import TTSClient

    cfg = Config.load()
    url = f"http://{cfg.tts.host}:{cfg.tts.port}/config"
    client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")
    healthy = asyncio.run(client.health())

    if not healthy:
        click.echo(f"TTS server is not running on {cfg.tts.host}:{cfg.tts.port}", err=True)
        click.echo("Start it with: claudible start", err=True)
        sys.exit(1)

    click.echo(f"Opening {url}")
    webbrowser.open(url)
