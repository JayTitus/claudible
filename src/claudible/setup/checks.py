"""Setup check/install functions for claudible."""

from __future__ import annotations

import grp
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import click


# --- Helpers ---

def _confirm(prompt: str, auto_yes: bool) -> bool:
    """Ask user for confirmation, or auto-accept if --yes."""
    if auto_yes:
        click.echo(f"  {prompt} (auto-yes)")
        return True
    return click.confirm(f"  {prompt}", default=True)


def _pass(msg: str) -> bool:
    click.echo(click.style(f"  [OK] {msg}", fg="green"))
    return True


def _warn(msg: str) -> bool:
    click.echo(click.style(f"  [!!] {msg}", fg="yellow"))
    return False


def _fail(msg: str) -> bool:
    click.echo(click.style(f"  [FAIL] {msg}", fg="red"))
    return False


# --- Check functions ---

def check_dirs() -> bool:
    """Create XDG directories."""
    from claudible.paths import ensure_dirs
    ensure_dirs()
    return _pass("XDG directories created")


def check_config() -> bool:
    """Write default config if missing."""
    from claudible.config import Config
    from claudible.paths import CONFIG_FILE

    if CONFIG_FILE.exists():
        return _pass(f"Config exists at {CONFIG_FILE}")
    cfg = Config()
    cfg.save()
    return _pass(f"Default config written to {CONFIG_FILE}")


def check_hook() -> bool:
    """Install Claude Code stop hook."""
    from claudible.hooks.installer import install_hook, is_installed

    if is_installed():
        return _pass("Claude Code stop hook already installed")
    install_hook()
    return _pass("Claude Code stop hook installed")


def check_nerd_dictation(auto_yes: bool = False) -> bool:
    """Detect or install nerd-dictation."""
    nd_bin = shutil.which("nerd-dictation")
    if nd_bin:
        return _pass(f"nerd-dictation found at {nd_bin}")

    # Check common clone location
    clone_dir = Path.home() / ".local" / "src" / "nerd-dictation"
    local_bin = Path.home() / ".local" / "bin" / "nerd-dictation"

    if clone_dir.exists() and (clone_dir / "nerd-dictation").exists():
        if not local_bin.exists():
            local_bin.parent.mkdir(parents=True, exist_ok=True)
            local_bin.symlink_to(clone_dir / "nerd-dictation")
        return _pass(f"nerd-dictation symlinked to {local_bin}")

    if not _confirm("nerd-dictation not found. Clone from GitHub?", auto_yes):
        return _warn("nerd-dictation not installed — STT will not work")

    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "https://github.com/ideasman42/nerd-dictation.git",
             str(clone_dir)],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return _fail(f"Failed to clone nerd-dictation: {e}")

    local_bin.parent.mkdir(parents=True, exist_ok=True)
    if not local_bin.exists():
        local_bin.symlink_to(clone_dir / "nerd-dictation")

    return _pass(f"nerd-dictation cloned and symlinked to {local_bin}")


def check_vosk_model(auto_yes: bool = False) -> bool:
    """Detect or download VOSK small English model."""
    vosk_dir = Path.home() / ".local" / "share" / "vosk"
    model_dir = vosk_dir / "small"

    if model_dir.exists() and any(model_dir.iterdir()):
        return _pass(f"VOSK model found at {model_dir}")

    if not _confirm("VOSK model not found. Download vosk-model-small-en-us-0.15?", auto_yes):
        return _warn("VOSK model not installed — STT will not work")

    url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    zip_path = vosk_dir / "vosk-model-small-en-us-0.15.zip"
    vosk_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"    Downloading {url} ...")
    try:
        urlretrieve(url, zip_path)
    except Exception as e:
        return _fail(f"Download failed: {e}")

    click.echo("    Extracting...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(vosk_dir)
        # The zip extracts as vosk-model-small-en-us-0.15/ — rename to small/
        extracted = vosk_dir / "vosk-model-small-en-us-0.15"
        if extracted.exists():
            if model_dir.exists():
                shutil.rmtree(model_dir)
            extracted.rename(model_dir)
        zip_path.unlink(missing_ok=True)
    except Exception as e:
        return _fail(f"Extraction failed: {e}")

    return _pass(f"VOSK model installed at {model_dir}")


def check_input_group(auto_yes: bool = False) -> bool:
    """Check if user is in the 'input' group (needed for evdev PTT)."""
    username = os.getenv("USER", "")
    try:
        input_group = grp.getgrnam("input")
    except KeyError:
        return _warn("'input' group does not exist — PTT may not work")

    if username in input_group.gr_mem or os.getgid() == input_group.gr_gid:
        return _pass(f"User '{username}' is in 'input' group")

    return _warn(
        f"User '{username}' not in 'input' group (needed for PTT). Run:\n"
        f"      sudo usermod -aG input {username}  # then log out and back in"
    )


def check_gpu() -> bool:
    """Check if CUDA is available via PyTorch."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return _pass(f"CUDA available: {name}")
        else:
            return _warn("CUDA not available — TTS will be slow on CPU")
    except ImportError:
        return _warn("PyTorch not installed — install with [tts] extra")


def check_transformers_version() -> bool:
    """Warn if transformers version is too new for Coqui TTS."""
    try:
        import transformers
        version = transformers.__version__
        major, minor = (int(x) for x in version.split(".")[:2])
        if major > 4 or (major == 4 and minor > 44):
            return _warn(
                f"transformers=={version} — Coqui TTS needs <=4.44.2 "
                "(pip install transformers==4.44.2)"
            )
        return _pass(f"transformers=={version} (compatible)")
    except ImportError:
        return _warn("transformers not installed — install with [tts] extra")


def check_torchcodec() -> bool:
    """Warn if torchcodec is missing when torchaudio is installed."""
    try:
        import torchaudio
        try:
            import torchcodec  # noqa: F401
            return _pass("torchcodec installed")
        except ImportError:
            return _warn("torchaudio installed but torchcodec missing (pip install torchcodec)")
    except ImportError:
        # torchaudio not installed, no concern
        return _pass("torchaudio not installed — torchcodec not needed")


def check_ld_library_path() -> bool:
    """Warn if nvidia-cudnn lib dir is not in LD_LIBRARY_PATH."""
    ld_path = os.environ.get("LD_LIBRARY_PATH", "")

    # Find nvidia cudnn package path
    try:
        import nvidia.cudnn as _cudnn  # noqa: F401
        # nvidia.cudnn may be a namespace package with __file__=None
        if _cudnn.__file__:
            cudnn_path = Path(_cudnn.__file__).parent / "lib"
        else:
            # Fall back to the package's loader path
            import importlib.util
            spec = importlib.util.find_spec("nvidia.cudnn")
            if spec and spec.submodule_search_locations:
                cudnn_path = Path(list(spec.submodule_search_locations)[0]) / "lib"
            else:
                return _pass("nvidia-cudnn installed but lib path not detected")
        if str(cudnn_path) in ld_path:
            return _pass("nvidia-cudnn in LD_LIBRARY_PATH")
        else:
            return _warn(
                f"nvidia-cudnn lib not in LD_LIBRARY_PATH. Add:\n"
                f"      export LD_LIBRARY_PATH={cudnn_path}:$LD_LIBRARY_PATH"
            )
    except ImportError:
        return _pass("nvidia-cudnn not installed (not needed if using system cuDNN)")


def check_voices(auto_yes: bool = False) -> bool:
    """Warn if no voices are installed."""
    from claudible.tts.voices import list_voices

    voices = list_voices()
    if voices:
        return _pass(f"{len(voices)} voice(s) installed")

    click.echo(click.style("  [!!] No voices installed", fg="yellow"))
    if not _confirm("Download a default voice sample from Coqui/XTTS?", auto_yes):
        return _warn("No voices — TTS will fail until a voice is added")

    # Download the XTTS v2 default speaker wav from Coqui's HuggingFace
    from claudible.paths import VOICES_DIR

    voice_dir = VOICES_DIR / "default"
    voice_dir.mkdir(parents=True, exist_ok=True)
    wav_path = voice_dir / "sample.wav"

    url = "https://huggingface.co/coqui/XTTS-v2/resolve/main/samples/en_sample.wav"
    click.echo(f"    Downloading {url} ...")
    try:
        urlretrieve(url, wav_path)
    except Exception as e:
        return _fail(f"Download failed: {e}")

    return _pass(f"Default voice downloaded to {wav_path}")


def run_all_checks(auto_yes: bool = False, skip_gpu: bool = False) -> tuple[int, int]:
    """Run all checks and return (passed, total)."""
    click.echo("Running claudible setup checks...\n")

    results = []

    # Always run these
    results.append(("Directories", check_dirs()))
    results.append(("Config", check_config()))
    results.append(("Claude Code hook", check_hook()))
    results.append(("nerd-dictation", check_nerd_dictation(auto_yes)))
    results.append(("VOSK model", check_vosk_model(auto_yes)))
    results.append(("input group", check_input_group(auto_yes)))

    if not skip_gpu:
        results.append(("GPU/CUDA", check_gpu()))
        results.append(("transformers", check_transformers_version()))
        results.append(("torchcodec", check_torchcodec()))
        results.append(("LD_LIBRARY_PATH", check_ld_library_path()))

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
