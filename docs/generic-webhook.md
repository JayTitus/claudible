# Generic Output Webhook

A runtime-agnostic ingest endpoint that lets any LLM tool send its output to claudible to be filtered, optionally rephrased through a persona, and spoken aloud.

The original Claude Code stop hook (`POST` triggered by Claude's hook system) stays in place. The generic webhook is the same processing pipeline exposed over HTTP so non-Claude tools can plug in without writing custom integrations.

## Endpoint

```
POST /v1/hook/output
Content-Type: application/json
```

Body schema:

| Field | Type | Required | Description |
|---|---|---|---|
| `tool` | string | yes | Free-form id of source runtime (`"ollama"`, `"foundry"`, `"codex"`, ...) |
| `content` | string | yes | The text to filter, rephrase, and speak |
| `persona` | string | no | Override the active persona for this call |
| `voice` | string | no | Override the TTS voice for this call |
| `mode` | string | no | `"full"` / `"questions"` / `"completion"` / `"off"`; default from config |
| `urgent` | bool | no | Bypass the speaking queue (reserved for a future change) |

Response:

```json
{ "ok": true, "tool": "ollama", "persona": "noir", "voice": "casey", "speak_length": 84, "urgent": false }
```

or

```json
{ "ok": false, "reason": "filtered empty" }
```

Speak failures are intentionally caught and reported as `ok: false`; the webhook never returns an HTTP 5xx for a TTS error. Voice is best-effort by design.

## Listing backend adapters

```
GET /v1/hook/backends
```

```json
{
  "backends": [
    {"name": "ollama", "label": "Ollama (OpenAI-compatible local server)", "detected": true, "installed": false, "details": ""},
    {"name": "foundry", "label": "Foundry Local", "detected": false, "installed": false, "details": ""},
    {"name": "openwebui", "label": "OpenWebUI", "detected": false, "installed": false, "details": ""},
    {"name": "generic", "label": "Generic CLI tool", "detected": false, "installed": false, "details": "parameterized; install with `claudible hook install generic <command>`"}
  ]
}
```

## CLI

```
claudible hook install ollama
claudible hook install foundry
claudible hook install openwebui
claudible hook install generic --command codex
claudible hook uninstall ollama
claudible hook status
```

## Backend integration patterns

### Ollama / Foundry Local / arbitrary CLI

Installer drops a shell wrapper at `~/.local/bin/<command>-claudible`:

1. Calls the underlying CLI with the original arguments
2. Tees output through `claudible-hook-fire` which POSTs to the webhook

```bash
# Instead of:
ollama run llama3.1 "explain quicksort"

# Use:
ollama-claudible run llama3.1 "explain quicksort"
```

The response prints to your terminal and is also spoken aloud.

### OpenWebUI

OpenWebUI is browser-hosted; there's no CLI to wrap. `claudible hook install openwebui` emits a Tampermonkey-compatible userscript at `~/.config/claudible/openwebui/claudible-openwebui.user.js`. Load it into your browser's userscript manager.

The script hooks OpenWebUI's streaming-completion DOM events and POSTs each completed response to the webhook.

### Claude Code

Unchanged — keep using `claudible hooks install` (with the `s`). It writes a stop hook entry into `~/.claude/settings.json` that calls `claudible.hooks.stop_hook`, which in turn calls the same pipeline as the webhook (just in-process instead of HTTP).

## Authentication

The webhook binds to localhost by default; LAN exposure requires explicit configuration. When the daemon is reachable beyond localhost, set `tts.token` in `~/.config/claudible/config.toml`:

```toml
[tts]
host = "0.0.0.0"
token = "long-random-string"
```

All `/v1/*` endpoints then require `Authorization: Bearer <token>`. The shell wrappers accept `--token` to pass it; the userscript embeds it at install time.

## Calling the webhook from your own code

```python
import httpx

async def speak(content: str, persona: str | None = None) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        await client.post(
            "http://127.0.0.1:5959/v1/hook/output",
            json={"tool": "my-app", "content": content, "persona": persona},
        )
```

```typescript
async function speak(content: string, persona?: string): Promise<void> {
  await fetch("http://127.0.0.1:5959/v1/hook/output", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool: "my-app", content, persona }),
  });
}
```

## See also

- [`architecture.md`](architecture.md) — system overview + audio pipeline
- [`roadmap.md`](roadmap.md) — what's coming next
