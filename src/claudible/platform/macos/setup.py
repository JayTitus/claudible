"""macOS setup backend — brew-based checks."""

from __future__ import annotations

import os
import shutil
import subprocess

import click

from claudible.platform.base import SetupBackend


def _pass(msg: str) -> bool:
    click.echo(click.style(f"  [OK] {msg}", fg="green"))
    return True


def _warn(msg: str) -> bool:
    click.echo(click.style(f"  [!!] {msg}", fg="yellow"))
    return False


class BrewSetup(SetupBackend):
    """brew-based setup checks for macOS."""

    def check_system_deps(self) -> bool:
        if not shutil.which("brew"):
            return _warn("Homebrew not installed — visit https://brew.sh")

        # On macOS we need fewer system deps
        needed = []
        if not shutil.which("portaudio"):
            # sounddevice needs portaudio
            try:
                result = subprocess.run(
                    ["brew", "list", "portaudio"],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    needed.append("portaudio")
            except FileNotFoundError:
                needed.append("portaudio")

        if needed:
            click.echo(f"  [..] Installing: {', '.join(needed)}")
            result = subprocess.run(
                ["brew", "install"] + needed,
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                return _warn(f"Failed to install: {', '.join(needed)}")

        return _pass("System dependencies satisfied")

    def check_input_permissions(self, auto_yes: bool = False) -> bool:
        # macOS uses Accessibility permissions, not input groups
        click.echo("  [!!] macOS requires Accessibility permissions for keyboard input.")
        click.echo("       Go to System Settings > Privacy & Security > Accessibility")
        click.echo("       and add your terminal application.")
        return _warn("Check Accessibility permissions manually")

    def get_system_info(self) -> dict:
        ram_gb = 0.0
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                ram_gb = int(result.stdout.strip()) / (1024**3)
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

        gpu = "not detected"
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if "Chipset Model:" in line or "Chip:" in line:
                    gpu = line.split(":", 1)[1].strip()
                    break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return {"gpu": gpu, "ram_gb": ram_gb}
