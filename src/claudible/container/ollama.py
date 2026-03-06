"""Podman container lifecycle manager for bundled Ollama."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time

from claudible.paths import OLLAMA_DATA_DIR

log = logging.getLogger(__name__)

CONTAINER_NAME = "claudible-ollama"
DEFAULT_PORT = 11435
IMAGE = "docker.io/ollama/ollama"


def _podman() -> str:
    """Return the podman binary path or raise."""
    path = shutil.which("podman")
    if not path:
        raise FileNotFoundError("podman not found — install with: sudo apt install podman")
    return path


def _has_nvidia_cdi() -> bool:
    """Check if nvidia-container-toolkit CDI is available."""
    try:
        result = subprocess.run(
            [_podman(), "info", "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        # CDI devices are listed when nvidia-container-toolkit is configured
        return "nvidia.com/gpu" in result.stdout
    except Exception:
        return False


def start_container(port: int = DEFAULT_PORT, gpu: bool = True) -> bool:
    """Start the Ollama container. Returns True on success."""
    podman = _podman()
    OLLAMA_DATA_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        podman, "run", "--replace", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"127.0.0.1:{port}:11434",
        "-v", f"{OLLAMA_DATA_DIR}:/root/.ollama:Z",
    ]

    if gpu and _has_nvidia_cdi():
        cmd.extend(["--device", "nvidia.com/gpu=all"])
        log.info("Starting Ollama container with GPU support")
    else:
        log.info("Starting Ollama container (CPU only)")

    cmd.append(IMAGE)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            log.error("Failed to start container: %s", result.stderr.strip())
            return False
        log.info("Ollama container started on port %d", port)
        return True
    except subprocess.TimeoutExpired:
        log.error("Container start timed out")
        return False


def stop_container() -> bool:
    """Stop and remove the Ollama container."""
    podman = _podman()
    try:
        subprocess.run(
            [podman, "stop", CONTAINER_NAME],
            capture_output=True, text=True, timeout=30,
        )
        subprocess.run(
            [podman, "rm", "-f", CONTAINER_NAME],
            capture_output=True, text=True, timeout=10,
        )
        log.info("Ollama container stopped")
        return True
    except Exception:
        log.error("Failed to stop container", exc_info=True)
        return False


def container_status() -> dict:
    """Get container status. Returns dict with 'running', 'status', 'port'."""
    try:
        podman = _podman()
        result = subprocess.run(
            [podman, "inspect", CONTAINER_NAME, "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"running": False, "status": "not found"}
        data = json.loads(result.stdout)
        if isinstance(data, list) and data:
            state = data[0].get("State", {})
            running = state.get("Running", False)
            return {
                "running": running,
                "status": state.get("Status", "unknown"),
            }
    except FileNotFoundError:
        return {"running": False, "status": "podman not installed"}
    except Exception:
        pass
    return {"running": False, "status": "unknown"}


def health_check(port: int = DEFAULT_PORT) -> bool:
    """Check if Ollama is responding on the given port."""
    import urllib.request

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _wait_for_ready(port: int = DEFAULT_PORT, timeout: float = 30.0) -> bool:
    """Wait for Ollama to become responsive."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if health_check(port):
            return True
        time.sleep(1)
    return False


def pull_model(model: str, port: int = DEFAULT_PORT) -> bool:
    """Pull a model into the running Ollama instance."""
    import urllib.request

    log.info("Pulling model %s ...", model)
    try:
        data = json.dumps({"name": model}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/pull",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            # Ollama streams JSON lines during pull
            for line in resp:
                line = line.decode().strip()
                if line:
                    status = json.loads(line)
                    s = status.get("status", "")
                    if "error" in status:
                        log.error("Pull error: %s", status["error"])
                        return False
                    if s:
                        log.debug("Pull: %s", s)
        log.info("Model %s pulled successfully", model)
        return True
    except Exception:
        log.error("Failed to pull model %s", model, exc_info=True)
        return False


def ensure_model(model: str, port: int = DEFAULT_PORT) -> bool:
    """Ensure a model is available, pulling if needed."""
    models = list_models(port)
    for m in models:
        if m.get("name", "").startswith(model.split(":")[0]):
            # Check for exact tag match
            if m.get("name") == model or model in m.get("name", ""):
                return True
    return pull_model(model, port)


def list_models(port: int = DEFAULT_PORT) -> list[dict]:
    """List models available in the Ollama instance."""
    import urllib.request

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("models", [])
    except Exception:
        return []
