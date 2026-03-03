"""RNNoise noise suppression via PipeWire filter-chain."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

log = logging.getLogger(__name__)

LADSPA_DIR = Path.home() / ".local" / "lib" / "ladspa"
LADSPA_SO = "librnnoise_ladspa.so"
PIPEWIRE_CONF_DIR = Path.home() / ".config" / "pipewire" / "filter-chain.conf.d"
PIPEWIRE_CONF_FILE = PIPEWIRE_CONF_DIR / "99-claudible-rnnoise.conf"

# PipeWire filter-chain config for mono RNNoise
RNNOISE_PIPEWIRE_CONF = """\
# Claudible RNNoise noise suppression filter
# Creates a virtual mic "rnnoise_source" with background noise removed.

context.modules = [
    {{ name = libpipewire-module-filter-chain
        args = {{
            node.description = "RNNoise Noise Canceling Source"
            media.name        = "RNNoise Noise Canceling Source"
            filter.graph = {{
                nodes = [
                    {{
                        type   = ladspa
                        name   = rnnoise
                        plugin = {ladspa_so}
                        label  = noise_suppressor_mono
                        control = {{
                            "VAD Threshold (%)" = 50.0
                        }}
                    }}
                ]
            }}
            capture.props = {{
                node.name      = "effect_input.rnnoise"
                node.passive   = true
                audio.rate     = 48000
            }}
            playback.props = {{
                node.name      = "effect_output.rnnoise"
                media.class    = Audio/Source
                audio.rate     = 48000
            }}
        }}
    }}
]
"""


def _ladspa_search_paths() -> list[Path]:
    """Return directories to search for LADSPA plugins."""
    paths = [LADSPA_DIR]
    env_path = os.environ.get("LADSPA_PATH", "")
    if env_path:
        paths.extend(Path(p) for p in env_path.split(":") if p)
    paths.extend([
        Path("/usr/lib/ladspa"),
        Path("/usr/lib/x86_64-linux-gnu/ladspa"),
        Path("/usr/local/lib/ladspa"),
    ])
    return paths


def is_rnnoise_installed() -> bool:
    """Check if librnnoise_ladspa.so exists in any LADSPA path."""
    for d in _ladspa_search_paths():
        if (d / LADSPA_SO).exists():
            return True
    return False


def get_rnnoise_path() -> Path | None:
    """Return the path to librnnoise_ladspa.so, or None if not found."""
    for d in _ladspa_search_paths():
        so = d / LADSPA_SO
        if so.exists():
            return so
    return None


def is_rnnoise_active() -> bool:
    """Check if the RNNoise PipeWire filter node is running."""
    try:
        result = subprocess.run(
            ["pw-cli", "list-objects"],
            capture_output=True, text=True, timeout=5,
        )
        return "rnnoise" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_rnnoise(auto_yes: bool = False) -> bool:
    """Build librnnoise_ladspa.so from source and install to ~/.local/lib/ladspa/.

    Requires cmake and build-essential (C++ compiler).
    """
    if is_rnnoise_installed():
        click.echo("  RNNoise LADSPA plugin already installed")
        return True

    # Check build deps
    for tool in ("cmake", "make", "git"):
        if not shutil.which(tool):
            click.echo(click.style(
                f"  [!!] '{tool}' not found — needed to build RNNoise. "
                f"Install with: sudo apt install cmake build-essential git",
                fg="yellow",
            ))
            return False

    if not auto_yes and not click.confirm(
        "  Build and install RNNoise LADSPA plugin from source?", default=True
    ):
        return False

    click.echo("  [..] Cloning werman/noise-suppression-for-voice...")
    with tempfile.TemporaryDirectory(prefix="claudible-rnnoise-") as tmpdir:
        repo_dir = Path(tmpdir) / "noise-suppression-for-voice"
        try:
            subprocess.run(
                ["git", "clone", "--depth=1",
                 "https://github.com/werman/noise-suppression-for-voice.git",
                 str(repo_dir)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            click.echo(click.style(f"  [FAIL] Clone failed: {e.stderr}", fg="red"))
            return False

        click.echo("  [..] Building with cmake...")
        build_dir = repo_dir / "build"
        try:
            subprocess.run(
                ["cmake", "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release",
                 "-DBUILD_VST_PLUGIN=OFF", "-DBUILD_LV2_PLUGIN=OFF",
                 "-DBUILD_AU_PLUGIN=OFF",
                 str(repo_dir)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["cmake", "--build", str(build_dir), "--parallel"],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            click.echo(click.style(f"  [FAIL] Build failed: {e.stderr[-500:]}", fg="red"))
            return False

        # Find the built .so
        built_so = None
        for candidate in build_dir.rglob(LADSPA_SO):
            built_so = candidate
            break

        if not built_so:
            click.echo(click.style(
                "  [FAIL] Build succeeded but librnnoise_ladspa.so not found", fg="red"
            ))
            return False

        # Install
        LADSPA_DIR.mkdir(parents=True, exist_ok=True)
        dest = LADSPA_DIR / LADSPA_SO
        shutil.copy2(built_so, dest)
        click.echo(click.style(f"  [OK] Installed {dest}", fg="green"))
        return True


def enable_rnnoise() -> bool:
    """Deploy PipeWire filter-chain config and restart the service."""
    so_path = get_rnnoise_path()
    if not so_path:
        log.error("RNNoise LADSPA plugin not found — cannot enable")
        return False

    PIPEWIRE_CONF_DIR.mkdir(parents=True, exist_ok=True)
    conf = RNNOISE_PIPEWIRE_CONF.format(ladspa_so=LADSPA_SO)
    PIPEWIRE_CONF_FILE.write_text(conf)
    log.info("Wrote PipeWire config: %s", PIPEWIRE_CONF_FILE)

    # Set LADSPA_PATH so PipeWire can find the plugin
    ladspa_dir = str(so_path.parent)
    env = os.environ.copy()
    existing = env.get("LADSPA_PATH", "")
    if ladspa_dir not in existing:
        env["LADSPA_PATH"] = f"{ladspa_dir}:{existing}" if existing else ladspa_dir

    # Restart filter-chain to pick up the new config
    result = subprocess.run(
        ["systemctl", "--user", "restart", "filter-chain"],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        # filter-chain service might not exist; try pipewire restart
        log.warning("filter-chain restart failed (%s), trying pipewire restart",
                     result.stderr.strip())
        subprocess.run(
            ["systemctl", "--user", "restart", "pipewire"],
            capture_output=True, text=True,
        )

    log.info("RNNoise filter enabled")
    return True


def disable_rnnoise() -> bool:
    """Remove PipeWire filter-chain config and restart."""
    if PIPEWIRE_CONF_FILE.exists():
        PIPEWIRE_CONF_FILE.unlink()
        log.info("Removed PipeWire config: %s", PIPEWIRE_CONF_FILE)

    # Restart to remove the filter node
    subprocess.run(
        ["systemctl", "--user", "restart", "filter-chain"],
        capture_output=True, text=True,
    )
    # Fallback
    subprocess.run(
        ["systemctl", "--user", "restart", "pipewire"],
        capture_output=True, text=True,
    )

    log.info("RNNoise filter disabled")
    return True
