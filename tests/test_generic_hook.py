"""Tests for the runtime-agnostic generic hook + backend adapters."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from claudible.hooks.backends import (
    ADAPTERS,
    BackendStatus,
    FoundryAdapter,
    GenericAdapter,
    OllamaAdapter,
    OpenWebUIAdapter,
)


def test_adapters_registry_contains_known_backends() -> None:
    assert set(ADAPTERS) == {"ollama", "foundry", "openwebui", "generic"}


def test_ollama_adapter_status_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # Force a clean wrapper dir by re-importing module-level Path expressions
    adapter = OllamaAdapter()
    # The "detected" field uses `which("ollama")`, which we can't deterministically
    # control across envs — but the install state should be False on a clean home.
    status = adapter.status()
    assert isinstance(status, BackendStatus)
    assert status.name == "ollama"
    # On a fresh fake-HOME nothing's installed yet.
    # (We don't reload modules so the WRAPPER_DIR was captured at import time;
    # still verify the type contract holds.)


def test_ollama_install_creates_wrapper(tmp_path, monkeypatch) -> None:
    """install() should write a wrapper script under ~/.local/bin."""
    wrapper_dir = tmp_path / ".local" / "bin"

    with patch("claudible.hooks.backends.ollama.WRAPPER_DIR", wrapper_dir):
        adapter = OllamaAdapter()
        adapter.install(host="127.0.0.1", port=5959, token=None)
        target = wrapper_dir / "ollama-claudible"
        assert target.exists()
        body = target.read_text()
        assert "ollama" in body
        assert "127.0.0.1" in body
        assert "5959" in body
        assert (target.stat().st_mode & 0o111) != 0  # executable

        adapter.uninstall()
        assert not target.exists()


def test_foundry_install_creates_wrapper(tmp_path) -> None:
    wrapper_dir = tmp_path / ".local" / "bin"
    with patch("claudible.hooks.backends.foundry.WRAPPER_DIR", wrapper_dir):
        adapter = FoundryAdapter()
        adapter.install(host="127.0.0.1", port=5959, token="abc")
        target = wrapper_dir / "foundry-claudible"
        assert target.exists()
        body = target.read_text()
        assert "foundry" in body
        assert "--token abc" in body


def test_openwebui_writes_userscript(tmp_path) -> None:
    artifact_dir = tmp_path / ".config" / "claudible" / "openwebui"
    with patch("claudible.hooks.backends.openwebui.ARTIFACT_DIR", artifact_dir):
        adapter = OpenWebUIAdapter()
        adapter.install(host="127.0.0.1", port=5959, token=None)
        target = artifact_dir / "claudible-openwebui.user.js"
        assert target.exists()
        body = target.read_text()
        assert "Claudible — OpenWebUI bridge" in body
        assert "127.0.0.1" in body
        assert "/api/v1/hook/output" in body


def test_generic_adapter_requires_command() -> None:
    adapter = GenericAdapter()
    with pytest.raises(ValueError, match="requires a command"):
        adapter.install(host="127.0.0.1", port=5959)


def test_generic_install(tmp_path) -> None:
    wrapper_dir = tmp_path / ".local" / "bin"
    with patch("claudible.hooks.backends.generic.WRAPPER_DIR", wrapper_dir):
        adapter = GenericAdapter("mytool")
        adapter.install(host="127.0.0.1", port=5959)
        target = wrapper_dir / "mytool-claudible"
        assert target.exists()
        assert "mytool " in target.read_text()


def test_process_output_filters_empty() -> None:
    """Empty content should short-circuit cleanly."""
    from claudible.hooks.generic import process_output

    result = asyncio.run(process_output(tool="test", content="   "))
    assert result == {"ok": False, "reason": "empty content"}


def test_process_output_mode_off() -> None:
    """mode=off should produce no speech regardless of content."""
    from claudible.hooks.generic import process_output

    result = asyncio.run(process_output(tool="test", content="hello world", mode="off"))
    assert result["ok"] is False
    assert result["reason"] == "mode=off"


def test_hook_fire_main_with_empty_file(tmp_path) -> None:
    """hook-fire should exit 0 silently on empty content."""
    from claudible.hooks import fire

    empty = tmp_path / "empty.txt"
    empty.write_text("")

    rc = fire.main.__wrapped__ if hasattr(fire.main, "__wrapped__") else None  # noqa: F841
    # Argparse + main() — easier to invoke main() directly with sys.argv patched.
    import sys

    saved = sys.argv
    try:
        sys.argv = [
            "claudible-hook-fire",
            "--tool", "test",
            "--file", str(empty),
            "--host", "127.0.0.1",
            "--port", "59599",  # closed port; would 404 if non-empty
        ]
        rc = fire.main()
    finally:
        sys.argv = saved
    assert rc == 0
