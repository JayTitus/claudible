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
    """Add a voice from a WAV file."""
    from claudible.tts.voices import add_voice

    voice = add_voice(name, wav_file)
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
    """Full interactive setup — checks deps, installs hooks, downloads models."""
    from claudible.setup.checks import run_all_checks

    passed, total = run_all_checks(auto_yes=yes, skip_gpu=skip_gpu)

    click.echo()
    if passed == total:
        click.echo("Ready! Next steps:")
        click.echo("  1. Start server:   claudible server")
        click.echo("  2. Test it:        claudible speak 'Hello world'")
        click.echo("  3. (Optional) PTT: claudible ptt")
        click.echo("  4. (Optional) TUI: claudible tui")
    else:
        click.echo("Fix the failures above and re-run: claudible install")
        sys.exit(1)


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
