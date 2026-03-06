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


def _pip_install(*packages: str) -> bool:
    """Install packages into the current Python environment (prefers uv, falls back to pip)."""
    uv = shutil.which("uv")
    if uv:
        result = subprocess.run(
            [uv, "pip", "install", "--python", sys.executable, *packages],
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", *packages],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        click.echo(click.style(f"      install error: {result.stderr.strip()[-200:]}", fg="red"))
    return result.returncode == 0


def _apt_install(*packages: str) -> bool:
    """Install system packages via apt, returns True on success."""
    # Check which are already installed
    missing = []
    for pkg in packages:
        result = subprocess.run(
            ["dpkg", "-s", pkg], capture_output=True, text=True,
        )
        if result.returncode != 0:
            missing.append(pkg)

    if not missing:
        return True

    click.echo(f"  [..] Installing system packages: {', '.join(missing)}")
    result = subprocess.run(
        ["sudo", "apt", "install", "-y"] + missing,
    )
    return result.returncode == 0


# All system (apt) packages needed for a full claudible install
SYSTEM_DEPS = [
    "libgirepository-2.0-dev",  # PyGObject build dep
    "libgirepository1.0-dev",   # PyGObject build dep (compat)
    "libcairo2-dev",            # PyGObject build dep
    "gir1.2-ayatanaappindicator3-0.1",  # System tray on KDE/GNOME
    "xdotool",                  # nerd-dictation types into focused window (X11)
    "cmake",                    # RNNoise LADSPA plugin build
    "build-essential",          # RNNoise LADSPA plugin build (C++ compiler)
    "podman",                   # Managed Ollama container for STT correction + rephrase
]

# Python packages to verify/fix — these are also in pyproject.toml dependencies,
# but we check explicitly because version pins can be overridden by transitive deps.
PYTHON_DEPS = [
    "transformers==4.44.2",  # Coqui TTS needs <=4.44 (TTS may pull newer)
    "torchcodec",            # torchaudio runtime dep
    "vosk",                  # nerd-dictation STT backend
    "PyGObject",             # pystray AppIndicator backend
]


def check_system_deps() -> bool:
    """Install all required system (apt) packages in one sudo call."""
    return _apt_install(*SYSTEM_DEPS) and _pass("System packages installed")


def check_python_deps() -> bool:
    """Install all required Python packages in one call."""
    # Check what's already satisfied
    missing = []
    for dep in PYTHON_DEPS:
        pkg_name = dep.split("==")[0].split(">=")[0].split("<=")[0]
        version_pin = dep.split("==")[1] if "==" in dep else None

        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg_name],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            missing.append(dep)
        elif version_pin:
            # Check version matches pin
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    installed = line.split(":", 1)[1].strip()
                    if installed != version_pin:
                        missing.append(dep)
                    break

    if not missing:
        return _pass("Python dependencies satisfied")

    click.echo(f"  [..] Installing: {', '.join(missing)}")

    # Clear uv build cache for PyGObject if system deps were just installed
    # (stale cache can cause build failures)
    uv = shutil.which("uv")
    if uv and any("PyGObject" in d for d in missing):
        subprocess.run([uv, "cache", "clean", "pygobject"], capture_output=True)

    if _pip_install(*missing):
        return _pass("Python dependencies installed")
    return _warn(f"Failed to install: {', '.join(missing)}")


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


VOSK_MODELS = [
    {
        "name": "large",
        "label": "Large — best accuracy (recommended)",
        "zip": "vosk-model-en-us-0.22",
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip",
        "size": "1.8 GB",
        "wer": "5.69%",
        "ram": "~2 GB",
        "note": "Best recognition. Needs 2+ GB RAM. GPU not required (CPU-only).",
    },
    {
        "name": "medium",
        "label": "Medium — good balance",
        "zip": "vosk-model-en-us-0.22-lgraph",
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip",
        "size": "128 MB",
        "wer": "7.82%",
        "ram": "~400 MB",
        "note": "Good accuracy, small footprint.",
    },
    {
        "name": "small",
        "label": "Small — lightweight",
        "zip": "vosk-model-small-en-us-0.15",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "size": "40 MB",
        "wer": "9.85%",
        "ram": "~100 MB",
        "note": "Lowest accuracy. Best for low-end hardware / Raspberry Pi.",
    },
    {
        "name": "gigaspeech",
        "label": "Gigaspeech — podcast-optimized",
        "zip": "vosk-model-en-us-0.42-gigaspeech",
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.42-gigaspeech.zip",
        "size": "2.3 GB",
        "wer": "5.64%",
        "ram": "~2.5 GB",
        "note": "Trained on Gigaspeech. Best for podcasts and long-form speech.",
    },
]


def download_vosk_model(model_name: str) -> str:
    """Download and install a VOSK model by name. Returns status message.

    Raises ValueError if model not found, RuntimeError on download/extract failure.
    """
    model_info = None
    for m in VOSK_MODELS:
        if m["name"] == model_name:
            model_info = m
            break
    if not model_info:
        raise ValueError(f"Unknown VOSK model: {model_name}")

    vosk_dir = Path.home() / ".local" / "share" / "vosk"
    model_dir = vosk_dir / model_info["name"]

    if model_dir.exists() and any(model_dir.iterdir()):
        return f"Model '{model_name}' already installed"

    vosk_dir.mkdir(parents=True, exist_ok=True)
    zip_path = vosk_dir / f"{model_info['zip']}.zip"

    try:
        urlretrieve(model_info["url"], zip_path)
    except Exception as e:
        raise RuntimeError(f"Download failed: {e}")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(vosk_dir)
        extracted = vosk_dir / model_info["zip"]
        if extracted.exists():
            if model_dir.exists():
                shutil.rmtree(model_dir)
            extracted.rename(model_dir)
        zip_path.unlink(missing_ok=True)
    except Exception as e:
        raise RuntimeError(f"Extraction failed: {e}")

    return f"Model '{model_name}' installed ({model_info['size']})"


def _get_gpu_info() -> str:
    """Detect GPU and return a summary string."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_mem / (1024**3)
            return f"{name} ({vram:.0f} GB VRAM)"
    except Exception:
        pass
    return "not detected"


def _get_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb / (1024**2)
    except Exception:
        pass
    return 0.0


def check_vosk_model(auto_yes: bool = False) -> bool:
    """Detect or download a VOSK English model with quality selection."""
    vosk_dir = Path.home() / ".local" / "share" / "vosk"

    # Check for any existing model
    from claudible.config import Config
    cfg = Config.load()
    model_name = cfg.stt.vosk_model
    model_dir = vosk_dir / model_name

    if model_dir.exists() and any(model_dir.iterdir()):
        # Show which model and its quality
        for m in VOSK_MODELS:
            if m["name"] == model_name:
                return _pass(f"VOSK model '{model_name}' installed (WER {m['wer']}, {m['size']})")
        return _pass(f"VOSK model found at {model_dir}")

    # Show hardware info to help user choose
    gpu_info = _get_gpu_info()
    ram_gb = _get_ram_gb()
    click.echo(f"  Hardware: GPU={gpu_info}, RAM={ram_gb:.0f} GB")
    click.echo()
    click.echo("  Available VOSK speech recognition models:")
    click.echo()

    for i, m in enumerate(VOSK_MODELS, 1):
        default = " (default)" if i == 1 else ""
        click.echo(f"    {i}. {m['label']}{default}")
        click.echo(f"       Download: {m['size']}  |  Word error rate: {m['wer']}  |  RAM: {m['ram']}")
        click.echo(f"       {m['note']}")
        click.echo()

    if auto_yes:
        choice_idx = 0  # large
    else:
        choice = click.prompt(
            "  Choose model",
            type=click.IntRange(1, len(VOSK_MODELS)),
            default=1,
        )
        choice_idx = choice - 1

    model = VOSK_MODELS[choice_idx]
    model_dir = vosk_dir / model["name"]

    click.echo(f"    Downloading {model['label']} ({model['size']})...")
    vosk_dir.mkdir(parents=True, exist_ok=True)
    zip_path = vosk_dir / f"{model['zip']}.zip"

    try:
        urlretrieve(model["url"], zip_path)
    except Exception as e:
        return _fail(f"Download failed: {e}")

    click.echo("    Extracting...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(vosk_dir)
        extracted = vosk_dir / model["zip"]
        if extracted.exists():
            if model_dir.exists():
                shutil.rmtree(model_dir)
            extracted.rename(model_dir)
        zip_path.unlink(missing_ok=True)
    except Exception as e:
        return _fail(f"Extraction failed: {e}")

    # Update config with chosen model name
    cfg.stt.vosk_model = model["name"]
    cfg.save()

    return _pass(f"VOSK model '{model['name']}' installed (WER {m['wer']}, {m['size']})")


def check_input_group(auto_yes: bool = False) -> bool:
    """Check if user is in the 'input' group (needed for evdev PTT)."""
    username = os.getenv("USER", "")
    try:
        input_group = grp.getgrnam("input")
    except KeyError:
        return _warn("'input' group does not exist — PTT may not work")

    if username in input_group.gr_mem or os.getgid() == input_group.gr_gid:
        return _pass(f"User '{username}' is in 'input' group")

    if auto_yes or _confirm(
        f"User '{username}' not in 'input' group (needed for PTT). Add now (requires sudo)?",
        auto_yes,
    ):
        import subprocess

        result = subprocess.run(
            ["sudo", "usermod", "-aG", "input", username],
            capture_output=True,
        )
        if result.returncode == 0:
            return _pass(f"User '{username}' added to 'input' group (log out and back in to activate)")
        else:
            return _warn(
                f"Failed to add user to 'input' group. Run manually:\n"
                f"      sudo usermod -aG input {username}  # then log out and back in"
            )

    return _warn(
        f"User '{username}' not in 'input' group (needed for PTT). Run:\n"
        f"      sudo usermod -aG input {username}  # then log out and back in"
    )


def check_vosk_pip() -> bool:
    """Verify vosk Python package is installed."""
    try:
        import vosk  # noqa: F401
        return _pass("vosk Python package installed")
    except ImportError:
        return _warn("vosk not installed — STT will not work")


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
    """Verify transformers is the right version (installed by earlier check)."""
    try:
        import transformers

        version = transformers.__version__
        major, minor = (int(x) for x in version.split(".")[:2])
        if major > 4 or (major == 4 and minor > 44):
            return _warn(f"transformers=={version} — needs <=4.44.2")
        return _pass(f"transformers=={version} (compatible)")
    except ImportError:
        return _warn("transformers not installed")


def check_torchcodec() -> bool:
    """Verify torchcodec is installed if torchaudio needs it."""
    try:
        import torchaudio  # noqa: F401
        try:
            import torchcodec  # noqa: F401
            return _pass("torchcodec installed")
        except ImportError:
            return _warn("torchcodec missing")
    except ImportError:
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
            # Auto-fix: set it for this process and note the daemon handles it
            os.environ["LD_LIBRARY_PATH"] = f"{cudnn_path}:{ld_path}" if ld_path else str(cudnn_path)
            return _pass(f"nvidia-cudnn added to LD_LIBRARY_PATH ({cudnn_path})")
    except ImportError:
        return _pass("nvidia-cudnn not installed (not needed if using system cuDNN)")


def check_appindicator() -> bool:
    """Verify PyGObject + AppIndicator are working (deps installed by earlier checks)."""
    # Ensure system typelibs are visible
    sys_typelib = "/usr/lib/x86_64-linux-gnu/girepository-1.0"
    if os.path.isdir(sys_typelib):
        existing = os.environ.get("GI_TYPELIB_PATH", "")
        if sys_typelib not in existing:
            os.environ["GI_TYPELIB_PATH"] = f"{sys_typelib}:{existing}" if existing else sys_typelib

    try:
        import gi
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3  # noqa: F401
        return _pass("AppIndicator support (PyGObject + AyatanaAppIndicator3)")
    except ImportError:
        return _warn("PyGObject not installed — run claudible install again")
    except ValueError:
        return _warn("AyatanaAppIndicator3 typelib not found")


def check_gui_deps() -> bool:
    """Check if pystray and Pillow are installed."""
    missing = []
    try:
        import pystray  # noqa: F401
    except ImportError:
        missing.append("pystray")
    except (ValueError, Exception) as exc:
        # pystray import can fail if GTK typelibs are missing
        return _warn(f"pystray installed but GTK backend failed: {exc}")
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        missing.append("Pillow")

    if missing:
        deps = ", ".join(missing)
        return _warn(f"GUI deps missing: {deps}")
    return _pass("GUI deps installed (pystray, Pillow)")


def check_rnnoise(auto_yes: bool = False) -> bool:
    """Detect RNNoise LADSPA plugin, offer to build/install if missing."""
    from claudible.stt.noise import install_rnnoise, is_rnnoise_installed

    if is_rnnoise_installed():
        return _pass("RNNoise LADSPA plugin installed")

    click.echo(click.style(
        "  [!!] RNNoise LADSPA plugin not found — noise suppression unavailable",
        fg="yellow",
    ))
    if _confirm("Build and install RNNoise from source?", auto_yes):
        if install_rnnoise(auto_yes=True):
            return _pass("RNNoise LADSPA plugin built and installed")
        return _fail("RNNoise build failed")
    return _warn("RNNoise not installed — noise suppression will not work")


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

    # Phase 1: Install all dependencies upfront (one sudo, one pip call)
    click.echo(click.style("  --- Installing dependencies ---", bold=True))
    results.append(("System packages", check_system_deps()))
    results.append(("Python packages", check_python_deps()))
    click.echo()

    # Phase 2: Verify everything works
    click.echo(click.style("  --- Verifying setup ---", bold=True))
    results.append(("Directories", check_dirs()))
    results.append(("Config", check_config()))
    results.append(("Claude Code hook", check_hook()))
    results.append(("nerd-dictation", check_nerd_dictation(auto_yes)))
    results.append(("VOSK model", check_vosk_model(auto_yes)))
    results.append(("vosk package", check_vosk_pip()))
    results.append(("input group", check_input_group(auto_yes)))
    results.append(("RNNoise", check_rnnoise(auto_yes)))

    if not skip_gpu:
        results.append(("GPU/CUDA", check_gpu()))
        results.append(("transformers", check_transformers_version()))
        results.append(("torchcodec", check_torchcodec()))
        results.append(("LD_LIBRARY_PATH", check_ld_library_path()))

    results.append(("AppIndicator", check_appindicator()))
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
