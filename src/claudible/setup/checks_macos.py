"""macOS-specific setup checks for claudible.

Replaces the Linux-oriented checks in checks.py with macOS equivalents.
Reuses cross-platform checks (VOSK model, GPU, voices) from checks.py.
"""

from __future__ import annotations

import shutil

import click


def _pass(msg: str) -> bool:
    click.echo(click.style(f"  [OK] {msg}", fg="green"))
    return True


def _warn(msg: str) -> bool:
    click.echo(click.style(f"  [!!] {msg}", fg="yellow"))
    return False


def check_brew() -> bool:
    """Check if Homebrew is installed."""
    if shutil.which("brew"):
        return _pass("Homebrew installed")
    return _warn("Homebrew not installed — visit https://brew.sh")


def check_portaudio() -> bool:
    """Check if portaudio is installed (needed by sounddevice)."""
    import subprocess

    result = subprocess.run(
        ["brew", "list", "portaudio"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return _pass("portaudio installed")
    return _warn("portaudio not installed — run: brew install portaudio")


def check_accessibility() -> bool:
    """Remind user about Accessibility permissions."""
    click.echo("  macOS requires Accessibility permissions for keyboard input.")
    click.echo("  System Settings > Privacy & Security > Accessibility")
    click.echo("  Add your terminal app (Terminal.app, iTerm2, etc.)")
    return _warn("Verify Accessibility permissions manually")


def run_all_checks_macos(auto_yes: bool = False, skip_gpu: bool = False) -> tuple[int, int]:
    """Run macOS-appropriate setup checks."""
    # Reuse cross-platform checks from checks.py
    from claudible.setup.checks import (
        check_config,
        check_dirs,
        check_gpu,
        check_gui_deps,
        check_hook,
        check_voices,
        check_vosk_model,
        check_vosk_pip,
    )

    click.echo("Running claudible setup checks (macOS)...\n")
    results = []

    # Phase 1: macOS-specific deps
    click.echo(click.style("  --- Platform checks ---", bold=True))
    results.append(("Homebrew", check_brew()))
    if shutil.which("brew"):
        results.append(("portaudio", check_portaudio()))
    results.append(("Accessibility", check_accessibility()))
    click.echo()

    # Phase 2: Cross-platform checks
    click.echo(click.style("  --- Verifying setup ---", bold=True))
    results.append(("Directories", check_dirs()))
    results.append(("Config", check_config()))
    results.append(("Claude Code hook", check_hook()))
    results.append(("VOSK model", check_vosk_model(auto_yes)))
    results.append(("vosk package", check_vosk_pip()))

    if not skip_gpu:
        results.append(("GPU/CUDA", check_gpu()))

    results.append(("GUI deps", check_gui_deps()))
    results.append(("Voices", check_voices(auto_yes)))

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    click.echo()
    if passed == total:
        click.echo(click.style(f"All {total}/{total} checks passed!", fg="green", bold=True))
    else:
        click.echo(f"{passed}/{total} checks passed.")
        click.echo("Failures:")
        for name, ok in results:
            if not ok:
                click.echo(f"  - {name}")

    return passed, total
