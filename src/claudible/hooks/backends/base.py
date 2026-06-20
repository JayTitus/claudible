"""Common interface for backend adapters.

A backend adapter knows how to:
  1. Detect whether the target runtime is installed locally
  2. Install / uninstall the wiring that forwards runtime output to claudible
  3. Report current install status

It does NOT call the runtime, parse runtime traffic, or proxy requests.
Those concerns live in the runtime itself (or in a separate proxy if needed).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BackendStatus:
    """Snapshot of an adapter's install state."""

    name: str
    detected: bool          # is the runtime present on this machine?
    installed: bool         # is the claudible hook wired up?
    details: str = ""       # human-readable extra info


class BackendAdapter(ABC):
    """Abstract base for runtime hook adapters."""

    #: Stable adapter id (e.g. "ollama"). Used in CLI + webhook payload.
    name: str = "<override>"

    #: Human-readable label for UI surfaces.
    label: str = "<override>"

    @abstractmethod
    def detect(self) -> bool:
        """Return True if the runtime appears installed on this machine."""

    @abstractmethod
    def install(self, *, host: str, port: int, token: str | None = None) -> None:
        """Set up the integration so runtime output reaches claudible.

        Implementations vary by runtime — may write a config file, register a
        proxy, install a shell wrapper, modify env, etc. Must be idempotent.
        """

    @abstractmethod
    def uninstall(self) -> None:
        """Reverse :meth:`install`. Must be idempotent."""

    @abstractmethod
    def status(self) -> BackendStatus:
        """Report detection + install state."""
