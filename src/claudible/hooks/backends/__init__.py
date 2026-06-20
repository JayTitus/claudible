"""Backend adapters for the generic output webhook.

Each adapter exposes a uniform interface for hook installation against a
specific LLM tool or runtime (Claude Code, Ollama, Foundry Local, OpenWebUI,
arbitrary CLI tools). Adapters never call into the runtime; they only set
up the wiring so that runtime output flows to ``/api/v1/hook/output``.
"""
from __future__ import annotations

from claudible.hooks.backends.base import BackendAdapter, BackendStatus
from claudible.hooks.backends.foundry import FoundryAdapter
from claudible.hooks.backends.generic import GenericAdapter
from claudible.hooks.backends.ollama import OllamaAdapter
from claudible.hooks.backends.openwebui import OpenWebUIAdapter

__all__ = [
    "BackendAdapter",
    "BackendStatus",
    "FoundryAdapter",
    "GenericAdapter",
    "OllamaAdapter",
    "OpenWebUIAdapter",
    "ADAPTERS",
]

ADAPTERS: dict[str, type[BackendAdapter]] = {
    "ollama": OllamaAdapter,
    "foundry": FoundryAdapter,
    "openwebui": OpenWebUIAdapter,
    "generic": GenericAdapter,
}
