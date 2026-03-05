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
    """Start the TTS server + system tray."""
    import threading

    from claudible.config import Config
    from claudible.lifecycle import is_running, read_pid, write_pid

    if is_running():
        pid = read_pid()
        click.echo(f"Claudible is already running (PID {pid}).")
        sys.exit(0)

    write_pid()
    cfg = Config.load()

    # Ensure nerd-dictation callback is current
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

    click.echo("Launching tray icon...")
    app = TrayApp()
    app.run()


@main.command()
def stop() -> None:
    """Stop the running claudible process."""
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
    """Restart claudible (stop + start via systemd or background process)."""
    import shutil
    import subprocess
    import time

    from claudible.lifecycle import is_running

    if is_running():
        ctx.invoke(stop)
        time.sleep(1)

    # Prefer systemd if the service is available
    if shutil.which("systemctl"):
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", "claudible"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                subprocess.run(["systemctl", "--user", "start", "claudible"], check=True)
                click.echo("Claudible started via systemd.")
                return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

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
    from claudible.stt.keybind import run_ptt

    cfg = Config.load()
    run_ptt(cfg)


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
    from claudible.stt.windows import read_window_state, validate_window

    state = read_window_state()
    wins = state.get("windows", {})
    if not wins:
        click.echo("  No windows registered.")
        return
    for slot, entry in sorted(wins.items()):
        wid = entry.get("window_id")
        title = entry.get("title", "")
        pid = entry.get("pid")
        process = entry.get("process")
        alive = validate_window(wid) if wid else False
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
    from claudible.stt.windows import register_window

    try:
        state = register_window(slot)
        entry = state.get("windows", {}).get(slot, {})
        click.echo(f"Registered slot {slot}: {entry.get('window_id')} ({entry.get('title', '')})")
    except RuntimeError as e:
        click.echo(f"Failed: {e}", err=True)
        sys.exit(1)


@windows.command("clear")
def windows_clear() -> None:
    """Clear all window registrations."""
    from claudible.stt.windows import clear_all_windows

    clear_all_windows()
    click.echo("All window registrations cleared.")


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
