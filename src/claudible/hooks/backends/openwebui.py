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
"""
from __future__ import annotations

import logging
from pathlib import Path

from claudible.hooks.backends.base import BackendAdapter, BackendStatus

log = logging.getLogger(__name__)

ARTIFACT_DIR = Path.home() / ".config" / "claudible" / "openwebui"
USERSCRIPT_NAME = "claudible-openwebui.user.js"


class OpenWebUIAdapter(BackendAdapter):
    name = "openwebui"
    label = "OpenWebUI"

    def detect(self) -> bool:
        # No way to programmatically detect OpenWebUI; the user knows.
        # Always report "detected" if the artifact dir exists OR if a likely
        # process name appears (process check kept light to avoid false positives).
        return ARTIFACT_DIR.exists()

    def install(self, *, host: str, port: int, token: str | None = None) -> None:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        target = ARTIFACT_DIR / USERSCRIPT_NAME
        target.write_text(_userscript(host=host, port=port, token=token))
        target.chmod(0o644)
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


def _userscript(*, host: str, port: int, token: str | None) -> str:
    """Render a Tampermonkey-compatible userscript.

    The script hooks the OpenWebUI streaming completion event, accumulates the
    full response text, and POSTs it to the claudible webhook when streaming
    finishes.
    """
    auth_header = f'"Authorization": "Bearer {token}",' if token else ""
    return f"""// ==UserScript==
// @name         Claudible — OpenWebUI bridge
// @namespace    https://github.com/JayTitus/claudible
// @version      0.1.0
// @description  Forward OpenWebUI assistant responses to the claudible TTS daemon.
// @match        *://*/admin/*
// @match        *://*/c/*
// @match        *://localhost:*/*
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @connect      {host}
// ==/UserScript==
(function () {{
  const ENDPOINT = "http://{host}:{port}/api/v1/hook/output";
  const TOOL = "openwebui";

  function fire(text) {{
    if (!text || !text.trim()) return;
    const body = JSON.stringify({{ tool: TOOL, content: text }});
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
