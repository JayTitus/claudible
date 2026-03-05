"""Interactive installation wizard for claudible."""

from __future__ import annotations

import sys
from pathlib import Path

import click


def _header(title: str) -> None:
    click.echo()
    click.echo(click.style(f"=== {title} ===", bold=True))
    click.echo()


def _step_checks(auto_yes: bool, skip_gpu: bool) -> bool:
    """Step 1: Run dependency checks."""
    _header("Step 1: Dependency Checks")
    from claudible.setup.checks import run_all_checks

    passed, total = run_all_checks(auto_yes=auto_yes, skip_gpu=skip_gpu)
    return passed == total


def _step_configure_voice(auto_yes: bool) -> str | None:
    """Step 2: Configure voice. Returns chosen voice name or None."""
    _header("Step 2: Configure Voice")

    from claudible.tts.voices import list_voices

    voices = list_voices()
    if voices:
        click.echo("Installed voices:")
        for i, v in enumerate(voices, 1):
            click.echo(f"  {i}. {v.name}")
        click.echo()

    # Offer to add a custom voice
    if not auto_yes and click.confirm("Add a custom voice sample?", default=False):
        wav_path = click.prompt("Path to WAV file", type=click.Path(exists=True))
        name = click.prompt("Voice name", default=Path(wav_path).stem)

        from claudible.tts.voices import process_voice_sample, validate_voice_sample

        issues = validate_voice_sample(Path(wav_path))
        if issues:
            for issue in issues:
                if issue.startswith("ERROR:"):
                    click.echo(click.style(f"  {issue}", fg="red"))
                else:
                    click.echo(click.style(f"  {issue}", fg="yellow"))
            errors = [i for i in issues if i.startswith("ERROR:")]
            if errors:
                click.echo("Cannot use this sample.")
                return None
            if not click.confirm("Continue with warnings?", default=True):
                return None

        voice = process_voice_sample(Path(wav_path), name)
        click.echo(click.style(f"  Voice '{voice.name}' added.", fg="green"))
        return name

    # Pick from existing
    voices = list_voices()
    if not voices:
        click.echo("  No voices installed. A default will be downloaded during checks.")
        return "default"

    if len(voices) == 1:
        click.echo(f"  Using voice: {voices[0].name}")
        return voices[0].name

    if auto_yes:
        return voices[0].name

    choice = click.prompt(
        "Choose voice number",
        type=click.IntRange(1, len(voices)),
        default=1,
    )
    return voices[choice - 1].name


def _step_configure_ptt(auto_yes: bool) -> str:
    """Step 3: Configure PTT key. Returns key name."""
    _header("Step 3: Configure Push-to-Talk Key")

    keys = [
        ("KEY_RIGHTCTRL", "Right Ctrl (default)"),
        ("KEY_SCROLLLOCK", "Scroll Lock"),
        ("KEY_PAUSE", "Pause/Break"),
        ("KEY_F13", "F13"),
        ("KEY_F14", "F14"),
        ("KEY_F15", "F15"),
        ("KEY_RIGHTALT", "Right Alt"),
    ]

    for i, (key, desc) in enumerate(keys, 1):
        click.echo(f"  {i}. {desc} ({key})")

    if auto_yes:
        click.echo("  Using default: KEY_RIGHTCTRL")
        return "KEY_RIGHTCTRL"

    choice = click.prompt(
        "Choose PTT key",
        type=click.IntRange(1, len(keys)),
        default=1,
    )
    return keys[choice - 1][0]


def _step_configure_toggle(auto_yes: bool) -> str:
    """Step 4: Configure toggle key. Returns key name."""
    _header("Step 4: Configure Global Toggle Key")

    click.echo("  The toggle key turns STT on/off globally (separate from PTT).")
    click.echo()

    keys = [
        ("KEY_SCROLLLOCK", "Scroll Lock (default)"),
        ("KEY_PAUSE", "Pause/Break"),
        ("KEY_F13", "F13"),
        ("KEY_F14", "F14"),
        ("KEY_F15", "F15"),
    ]

    for i, (key, desc) in enumerate(keys, 1):
        click.echo(f"  {i}. {desc} ({key})")

    if auto_yes:
        click.echo("  Using default: KEY_SCROLLLOCK")
        return "KEY_SCROLLLOCK"

    choice = click.prompt(
        "Choose toggle key",
        type=click.IntRange(1, len(keys)),
        default=1,
    )
    return keys[choice - 1][0]


def _step_test_voice(voice_name: str | None) -> None:
    """Step 5: Test voice output."""
    _header("Step 5: Test Voice")

    if not voice_name:
        click.echo("  Skipping — no voice configured.")
        return

    import asyncio

    from claudible.config import Config
    from claudible.tts.client import TTSClient

    cfg = Config.load()
    client = TTSClient(base_url=f"http://{cfg.tts.host}:{cfg.tts.port}")

    try:
        healthy = asyncio.run(client.health())
    except Exception:
        healthy = False

    if not healthy:
        click.echo("  TTS server not running. Skipping voice test.")
        click.echo("  Start the server with: claudible start")
        return

    click.echo(f"  Testing voice '{voice_name}'...")
    try:
        test_text = "Hello! This is claudible, your voice interface for Claude Code."
        ok = asyncio.run(client.speak(test_text, voice=voice_name))
        if ok:
            click.echo(click.style("  Voice test sent!", fg="green"))
            if not click.confirm("  Sound good?", default=True):
                click.echo("  You can change the voice later in Settings or config.toml.")
        else:
            click.echo("  Voice test failed — server may not have the voice loaded.")
    except Exception as e:
        click.echo(f"  Voice test error: {e}")


def _step_install_hook(auto_yes: bool) -> None:
    """Step 6: Install Claude Code stop hook."""
    _header("Step 6: Claude Code Hook")


    from claudible.hooks.installer import install_hook, is_installed

    if is_installed():
        click.echo("  Claude Code hook already installed.")
        return

    if auto_yes or click.confirm("Install Claude Code stop hook? (speaks responses automatically)", default=True):
        install_hook()
        click.echo(click.style("  Hook installed.", fg="green"))
    else:
        click.echo("  Skipped. Install later with: claudible hooks install")


def _step_install_voices() -> None:
    """Step 2: Install bundled persona voices."""
    _header("Step 2: Persona Voices")

    from claudible.data.bundled_voices import install_bundled_voices, setup_persona_voice_defaults

    installed = install_bundled_voices()
    if installed:
        click.echo(f"  Installed {len(installed)} voices: {', '.join(installed)}")
    else:
        click.echo("  All bundled voices already installed.")

    # Set up default persona → voice mappings
    from claudible.config import Config

    cfg = Config.load()
    defaults = setup_persona_voice_defaults()
    changed = False
    for persona, voice in defaults.items():
        if persona not in cfg.rephrase.persona_voices:
            cfg.rephrase.persona_voices[persona] = voice
            changed = True
    if changed:
        cfg.save()
        click.echo(f"  Set default voices for {len(defaults)} personas.")


def _step_install_rnnoise(auto_yes: bool) -> None:
    """Step 7: Build and install RNNoise LADSPA plugin."""
    _header("Step 7: RNNoise Noise Suppression")

    from claudible.stt.noise import install_rnnoise, is_rnnoise_installed

    if is_rnnoise_installed():
        click.echo("  RNNoise LADSPA plugin already installed.")
        return

    click.echo("  RNNoise removes background noise from your microphone input.")
    click.echo("  It builds from source and requires cmake + a C++ compiler.")
    click.echo()

    if auto_yes or click.confirm("Build and install RNNoise?", default=True):
        ok = install_rnnoise(auto_yes=True)
        if not ok:
            click.echo(click.style("  RNNoise install failed. You can retry later.", fg="yellow"))
    else:
        click.echo("  Skipped. Install later with: claudible install")


def _step_install_daemon(auto_yes: bool) -> None:
    """Step 8: Install and start systemd daemon."""
    _header("Step 8: Systemd Daemon")

    import subprocess

    from claudible.paths import CONFIG_DIR

    service_file = CONFIG_DIR.parent.parent / "systemd" / "user" / "claudible.service"

    if service_file.exists():
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", "claudible"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            click.echo("  Daemon already installed and enabled.")
            # Offer to restart in case config changed
            if not auto_yes and click.confirm("  Restart the daemon with new config?", default=True):
                subprocess.run(["systemctl", "--user", "restart", "claudible"], check=False)
                click.echo(click.style("  Daemon restarted.", fg="green"))
            return

    if auto_yes or click.confirm(
        "Install claudible as a systemd daemon? (starts on login)", default=True
    ):
        # Reuse the daemon install logic from CLI
        from claudible.paths import find_cudnn_lib

        import importlib.resources

        service_dest = Path.home() / ".config" / "systemd" / "user"
        service_dest.mkdir(parents=True, exist_ok=True)
        dest_file = service_dest / "claudible.service"

        ref = importlib.resources.files("claudible.systemd").joinpath("claudible.service")
        service_text = ref.read_text(encoding="utf-8")

        cudnn_path = find_cudnn_lib()
        if cudnn_path:
            lines = service_text.splitlines()
            insert_idx = None
            for i, line in enumerate(lines):
                if line.startswith("Environment="):
                    insert_idx = i + 1
            if insert_idx is not None:
                lines.insert(insert_idx, f"Environment=LD_LIBRARY_PATH={cudnn_path}")
                service_text = "\n".join(lines) + "\n"

        dest_file.write_text(service_text, encoding="utf-8")

        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "claudible"], check=True)
        subprocess.run(["systemctl", "--user", "start", "claudible"], check=True)
        click.echo(click.style("  Daemon installed, enabled, and started.", fg="green"))
    else:
        click.echo("  Skipped. Start manually with: claudible start")


def _step_summary(voice_name: str | None, ptt_key: str, toggle_key: str) -> None:
    """Final: Print config summary."""
    _header("Setup Complete")

    from claudible.config import Config
    from claudible.hooks.installer import is_installed

    cfg = Config.load()

    click.echo("  Configuration:")
    click.echo(f"    Voice:       {cfg.tts.voice}")
    click.echo(f"    PTT key:     {cfg.stt.push_to_talk_key}")
    click.echo(f"    Toggle key:  {cfg.stt.toggle_key}")
    click.echo(f"    TTS server:  {cfg.tts.host}:{cfg.tts.port}")
    click.echo(f"    Rephrase:    {'on' if cfg.rephrase.enabled else 'off'}")
    click.echo(f"    Hook:        {'installed' if is_installed() else 'not installed'}")
    click.echo()
    click.echo("  Useful commands:")
    click.echo("    claudible                  # check status")
    click.echo("    claudible stop             # stop server")
    click.echo("    claudible speak 'Hello'    # test speech")
    click.echo("    claudible voices list      # manage voices")


def run_wizard(auto_yes: bool = False, skip_gpu: bool = False) -> None:
    """Run the interactive installation wizard."""
    click.echo(click.style("Claudible Installation Wizard", bold=True, fg="cyan"))
    click.echo("This will check dependencies, configure your setup, and get you started.")

    # Step 1: Checks
    all_passed = _step_checks(auto_yes, skip_gpu)
    if not all_passed and not auto_yes:
        if not click.confirm("Some checks failed. Continue anyway?", default=True):
            click.echo("Fix the issues above and re-run: claudible install")
            sys.exit(1)

    # Step 2: Install bundled voices
    _step_install_voices()

    # Step 3: Voice
    voice_name = _step_configure_voice(auto_yes)

    # Step 3: PTT key
    ptt_key = _step_configure_ptt(auto_yes)

    # Step 4: Toggle key
    toggle_key = _step_configure_toggle(auto_yes)

    # Save config
    from claudible.config import Config

    cfg = Config.load()
    if voice_name:
        cfg.tts.voice = voice_name
    cfg.stt.push_to_talk_key = ptt_key
    cfg.stt.toggle_key = toggle_key
    cfg.save()
    click.echo(click.style("\n  Config saved.", fg="green"))

    # Generate nerd-dictation callback script
    try:
        from claudible.stt.callback import generate_callback

        generate_callback(cfg)
        click.echo("  nerd-dictation callback generated.")
    except Exception:
        pass

    # Step 5: Test voice
    if not auto_yes:
        _step_test_voice(voice_name)

    # Step 6: Hook
    _step_install_hook(auto_yes)

    # Step 7: RNNoise
    _step_install_rnnoise(auto_yes)

    # Step 8: Daemon
    _step_install_daemon(auto_yes)

    # Summary
    _step_summary(voice_name, ptt_key, toggle_key)
