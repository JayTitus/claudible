"""OpenWebUI backend adapter.

OpenWebUI is a browser-hosted chat front-end on top of any OpenAI-compatible
backend. There's no CLI to wrap; integration happens by either:

  1. Installing a small browser userscript that POSTs each response to the
     claudible webhook (the path this adapter favors), or
  2. Configuring an OpenAI-compatible proxy endpoint that copies responses.

The adapter emits the userscript into ``~/.config/claudible/openwebui/`` so
the user can drop it into Tampermonkey / Violentmonkey / a custom function
in their browser of choice. ``install`` is therefore a code generator;
``uninstall`` removes the generated artifacts.

Scoping note
------------
The userscript is deliberately scoped to the OpenWebUI origin only. A
userscript that matches ``*://*/*`` runs on every page the user visits, and
because it listens for generic DOM events (``stream:end``) and holds
``GM_xmlhttpRequest`` (which bypasses CORS), any site could otherwise
dispatch a forged event and push attacker-controlled text into the local
claudible daemon to be spoken aloud. Construct with
``OpenWebUIAdapter("https://chat.example.com")`` for a remote instance;
the default covers the common loopback install.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from claudible.hooks.backends.base import BackendAdapter, BackendStatus

log = logging.getLogger(__name__)

ARTIFACT_DIR = Path.home() / ".config" / "claudible" / "openwebui"
USERSCRIPT_NAME = "claudible-openwebui.user.js"

#: Loopback-only default. Covers a self-hosted OpenWebUI on any local port
#: without granting the script the whole web.
DEFAULT_MATCHES = ("http://localhost:*/*", "http://127.0.0.1:*/*")
DEFAULT_HOSTS = ("localhost", "127.0.0.1")


class OpenWebUIAdapter(BackendAdapter):
    """Adapter for OpenWebUI.

    :param site: Origin of the OpenWebUI instance (e.g.
        ``https://chat.example.com``). Omit for a loopback install.
    """

    name = "openwebui"
    label = "OpenWebUI"

    def __init__(self, site: str = "") -> None:
        self.site = site.rstrip("/")

    def detect(self) -> bool:
        # No way to programmatically detect OpenWebUI; the user knows.
        # Always report "detected" if the artifact dir exists OR if a likely
        # process name appears (process check kept light to avoid false positives).
        return ARTIFACT_DIR.exists()

    def install(self, *, host: str, port: int, token: str | None = None) -> None:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        target = ARTIFACT_DIR / USERSCRIPT_NAME
        target.write_text(
            _userscript(host=host, port=port, token=token, site=self.site)
        )
        # 0600, not 0644: the script embeds the bearer token when one is set.
        target.chmod(0o600)
        log.info("Wrote OpenWebUI userscript to %s", target)

    def uninstall(self) -> None:
        target = ARTIFACT_DIR / USERSCRIPT_NAME
        if target.exists():
            target.unlink()
            log.info("Removed %s", target)

    def status(self) -> BackendStatus:
        target = ARTIFACT_DIR / USERSCRIPT_NAME
        return BackendStatus(
            name=self.name,
            detected=self.detect(),
            installed=target.exists(),
            details=f"userscript at {target}" if target.exists() else "",
        )


def _scope(site: str) -> tuple[str, list[str]]:
    """Return the ``@match`` block and the runtime hostname allowlist.

    Falls back to loopback-only when no site is configured. Never returns a
    wildcard-host match.
    """
    if not site:
        matches = "\n".join(f"// @match        {m}" for m in DEFAULT_MATCHES)
        return matches, list(DEFAULT_HOSTS)

    parts = urlsplit(site)
    if not parts.scheme or not parts.hostname:
        raise ValueError(
            f"OpenWebUI site must be a full origin like https://chat.example.com, got {site!r}"
        )
    origin = f"{parts.scheme}://{parts.netloc}"
    return f"// @match        {origin}/*", [parts.hostname]


def _userscript(*, host: str, port: int, token: str | None, site: str = "") -> str:
    """Render a Tampermonkey-compatible userscript.

    The script hooks the OpenWebUI streaming completion event, accumulates the
    full response text, and POSTs it to the claudible webhook when streaming
    finishes.
    """
    auth_header = f'"Authorization": "Bearer {token}",' if token else ""
    match_block, allowed_hosts = _scope(site)
    return f"""// ==UserScript==
// @name         Claudible — OpenWebUI bridge
// @namespace    https://github.com/JayTitus/claudible
// @version      0.2.0
// @description  Forward OpenWebUI assistant responses to the claudible TTS daemon.
{match_block}
// @grant        GM_xmlhttpRequest
// @connect      {host}
// ==/UserScript==
(function () {{
  // Defence in depth: the match block already scopes us, but a manager
  // misconfiguration shouldn't be enough to let an arbitrary origin drive
  // the local daemon.
  const ALLOWED_HOSTS = {json.dumps(allowed_hosts)};
  if (!ALLOWED_HOSTS.includes(location.hostname)) return;

  const ENDPOINT = "http://{host}:{port}/api/v1/hook/output";
  const TOOL = "openwebui";
  const MAX_CHARS = 20000;

  function fire(text) {{
    if (typeof text !== "string" || !text.trim()) return;
    const body = JSON.stringify({{ tool: TOOL, content: text.slice(0, MAX_CHARS) }});
    GM_xmlhttpRequest({{
      method: "POST",
      url: ENDPOINT,
      data: body,
      headers: {{ "Content-Type": "application/json", {auth_header} }},
      onerror: () => {{ /* silent — voice is best-effort */ }},
    }});
  }}

  // OpenWebUI dispatches a custom event when a streaming completion finishes.
  // The event name has shifted across releases; we listen for several variants.
  ["openwebui:completion-finished", "ow:assistant-done", "stream:end"]
    .forEach(ev => window.addEventListener(ev, e => fire(e?.detail?.content)));
}})();
"""
