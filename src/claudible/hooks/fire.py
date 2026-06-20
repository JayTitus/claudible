"""Shell-callable CLI entrypoint for backend wrappers.

The Ollama / Foundry / generic shell wrappers tee output into a temp file
then exec this command:

.. code-block:: bash

    claudible-hook-fire --tool ollama --file /tmp/output.txt \
        --host 127.0.0.1 --port 5959 [--token TOKEN]

We deliberately keep this dependency-free so it works even when claudible
isn't on the wrapper's PATH (we install it at ``~/.local/bin``).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(prog="claudible-hook-fire")
    parser.add_argument("--tool", required=True, help="source runtime id (e.g. ollama)")
    parser.add_argument("--file", help="path to file containing the captured response")
    parser.add_argument("--content", help="response text (alternative to --file)")
    parser.add_argument("--persona", default=None)
    parser.add_argument("--voice", default=None)
    parser.add_argument("--mode", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5959, type=int)
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    if args.file:
        try:
            with open(args.file, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:
            print(f"hook-fire: failed to read {args.file}: {exc}", file=sys.stderr)
            return 2
    else:
        content = args.content or ""

    if not content.strip():
        # Nothing to speak. Exit clean — wrappers should not surface noise.
        return 0

    payload: dict[str, object] = {"tool": args.tool, "content": content}
    if args.persona:
        payload["persona"] = args.persona
    if args.voice:
        payload["voice"] = args.voice
    if args.mode:
        payload["mode"] = args.mode

    url = f"http://{args.host}:{args.port}/api/v1/hook/output"
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 — local URL
            resp.read()
    except urllib.error.URLError as exc:
        # Wrappers must not surface webhook failures; voice is best-effort.
        print(f"hook-fire: {exc}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via tests directly
    sys.exit(main())
