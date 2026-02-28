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
    from claudible.tts.voices import list_voices

    cfg = Config.load()
    voices = list_voices()
    hook_ok = is_installed()

    click.echo(f"claudible v{__version__}")
    click.echo(f"  TTS server:  {cfg.tts.host}:{cfg.tts.port}")
    click.echo(f"  TTS model:   {cfg.tts.model}")
    click.echo(f"  Voice:       {cfg.tts.voice}")
    click.echo(f"  Voices:      {len(voices)} installed")
    click.echo(f"  Rephrase:    {'on' if cfg.rephrase.enabled else 'off'}")
    click.echo(f"  Hook:        {'installed' if hook_ok else 'not installed'}")

    # Quick health check
    from claudible.tts.client import TTSClient

    client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")
    healthy = asyncio.run(client.health())
    click.echo(f"  Server:      {'running' if healthy else 'not running'}")


@main.command()
@click.option("--no-server", is_flag=True, help="Skip starting the TTS server")
def run(no_server: bool) -> None:
    """Start everything — TTS server + system tray."""
    import threading

    from claudible.config import Config

    cfg = Config.load()

    if not no_server:
        # Check if server is already running
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
@click.option("--host", default=None, help="Bind host")
@click.option("--port", default=None, type=int, help="Bind port")
def server(host: str | None, port: int | None) -> None:
    """Start the TTS server."""
    from claudible.config import Config
    from claudible.tts.server import run_server

    cfg = Config.load()
    run_server(host=host or cfg.tts.host, port=port or cfg.tts.port)


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


@main.group()
def daemon() -> None:
    """Manage the claudible systemd user service."""


@daemon.command("install")
def daemon_install() -> None:
    """Install and enable the systemd user service."""
    import importlib.resources
    import shutil

    service_dest = Path.home() / ".config" / "systemd" / "user"
    service_dest.mkdir(parents=True, exist_ok=True)
    dest_file = service_dest / "claudible.service"

    # Read the bundled service file
    ref = importlib.resources.files("claudible.systemd").joinpath("claudible.service")
    service_text = ref.read_text(encoding="utf-8")

    # Auto-detect nvidia-cudnn library path for LD_LIBRARY_PATH
    cudnn_path = _find_cudnn_lib()
    if cudnn_path:
        # Insert LD_LIBRARY_PATH line after the last Environment= line
        lines = service_text.splitlines()
        insert_idx = None
        for i, line in enumerate(lines):
            if line.startswith("Environment="):
                insert_idx = i + 1
        if insert_idx is not None:
            lines.insert(insert_idx, f"Environment=LD_LIBRARY_PATH={cudnn_path}")
            service_text = "\n".join(lines) + "\n"
        click.echo(f"  Detected cuDNN: {cudnn_path}")

    dest_file.write_text(service_text, encoding="utf-8")
    click.echo(f"  Service file written to {dest_file}")

    # Reload and enable
    import subprocess

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "claudible"], check=True)
    click.echo("  Service enabled. Run 'claudible daemon start' to start it.")


def _find_cudnn_lib() -> str | None:
    """Find the nvidia-cudnn library path inside the current Python environment."""
    try:
        import nvidia.cudnn

        # nvidia.cudnn may be a namespace package (__file__ is None), use __path__ instead
        for p in getattr(nvidia.cudnn, "__path__", []):
            cudnn_dir = Path(p) / "lib"
            if cudnn_dir.is_dir():
                return str(cudnn_dir)
    except ImportError:
        pass
    # Fallback: search site-packages
    for p in sys.path:
        candidate = Path(p) / "nvidia" / "cudnn" / "lib"
        if candidate.is_dir():
            return str(candidate)
    return None


@daemon.command("uninstall")
def daemon_uninstall() -> None:
    """Disable and remove the systemd user service."""
    import subprocess

    subprocess.run(
        ["systemctl", "--user", "disable", "--now", "claudible"],
        check=False,
    )
    service_file = Path.home() / ".config" / "systemd" / "user" / "claudible.service"
    if service_file.exists():
        service_file.unlink()
        click.echo("  Service file removed.")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    click.echo("  Service uninstalled.")


@daemon.command("start")
def daemon_start() -> None:
    """Start the claudible service."""
    import subprocess

    subprocess.run(["systemctl", "--user", "start", "claudible"], check=True)
    click.echo("claudible service started.")


@daemon.command("stop")
def daemon_stop() -> None:
    """Stop the claudible service."""
    import subprocess

    subprocess.run(["systemctl", "--user", "stop", "claudible"], check=True)
    click.echo("claudible service stopped.")


@daemon.command("status")
def daemon_status() -> None:
    """Show the service status."""
    import subprocess

    subprocess.run(["systemctl", "--user", "status", "claudible"], check=False)


@daemon.command("logs")
def daemon_logs() -> None:
    """Follow the service logs (Ctrl+C to stop)."""
    import subprocess

    subprocess.run(
        ["journalctl", "--user", "-u", "claudible", "-f", "--no-hostname"],
        check=False,
    )


@main.command()
@click.option("--yes", "-y", is_flag=True, help="Non-interactive mode (auto-accept prompts)")
@click.option("--skip-gpu", is_flag=True, help="Skip GPU/CUDA checks")
def install(yes: bool, skip_gpu: bool) -> None:
    """Full interactive setup — checks deps, configures voice, and gets you started."""
    from claudible.setup.wizard import run_wizard

    run_wizard(auto_yes=yes, skip_gpu=skip_gpu)


@main.command()
def tui() -> None:
    """Launch the Textual configuration TUI."""
    try:
        from claudible.tui.app import ClaudibleApp  # noqa: F811
    except ImportError:
        click.echo("Textual not installed. Install with: pip install claudible[tui]", err=True)
        sys.exit(1)

    app = ClaudibleApp()
    app.run()


@main.command()
def tray() -> None:
    """Launch the system tray icon."""
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

    app = TrayApp()
    app.run()


@main.command("config")
def config_cmd() -> None:
    """Open the configuration TUI (alias for 'tui')."""
    try:
        from claudible.tui.app import ClaudibleApp  # noqa: F811
    except ImportError:
        click.echo("Textual not installed. Install with: pip install claudible[tui]", err=True)
        sys.exit(1)

    app = ClaudibleApp()
    app.run()
