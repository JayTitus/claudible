# Claudible

## Overview
Voice interface for Claude Code: STT (nerd-dictation/VOSK) + TTS (Coqui XTTS v2) + personality rephrasing (Ollama).

## Project Structure
```
src/claudible/
├── cli.py              # Click CLI entry point
├── config.py           # TOML config with pydantic models
├── paths.py            # XDG-compliant directory paths
├── tts/                # Text-to-speech
│   ├── engine.py       # XTTS v2 model wrapper
│   ├── server.py       # FastAPI server (localhost:5959)
│   ├── client.py       # HTTP client for the server
│   ├── voices.py       # Voice profile management
│   └── audio.py        # Playback utilities
├── stt/                # Speech-to-text
│   ├── dictation.py    # nerd-dictation subprocess wrapper
│   └── keybind.py      # Push-to-talk via evdev
├── rephrase/           # Personality rephrasing
│   ├── ollama.py       # Ollama API integration
│   └── personas.py     # Built-in persona prompts
├── hooks/              # Claude Code integration
│   ├── stop_hook.py    # Stop hook (reads stdin JSON, sends to TTS)
│   └── installer.py    # Hook install/uninstall
├── tui/                # Textual TUI (legacy)
├── web/                # Browser config UI
│   ├── router.py       # FastAPI API routes (/api prefix)
│   └── static/         # HTML/CSS/JS SPA
└── systemd/            # User service units
```

## Key Architecture
- **TTS Server**: Persistent FastAPI daemon on localhost:5959, XTTS v2 on GPU, serves web config UI at /config
- **STT**: Wraps nerd-dictation as subprocess, push-to-talk via evdev
- **Rephrase**: Ollama API, transforms text AFTER Claude output but BEFORE TTS
- **Claude Code hook**: Stop hook reads `last_assistant_message` from stdin JSON, fire-and-forget to TTS server
- **Config**: TOML at ~/.config/claudible/config.toml
- **Voices**: ~/.local/share/claudible/voices/ (each voice = subdir with .wav)

## Install
- `uv tool install ./claudible --python 3.11` — global install
- `claudible install` — interactive setup (installs deps, daemon, hook)

## Dev extras
- `uv pip install -e ".[dev]"` — dev tools (pytest, ruff)
- `uv pip install -e ".[tui]"` — Textual TUI

## Testing
```bash
pytest tests/
```

## CLI
```
claudible                        # Status overview
claudible run                    # Start TTS server + tray icon
claudible server                 # Start TTS server only
claudible config                 # Open browser config UI (localhost:5959/config)
claudible ptt                    # Push-to-talk listener
claudible speak "text"           # Send text to TTS
claudible voices list            # List voices
claudible voices add NAME FILE   # Add voice from WAV
claudible voices combine NAME FILES...  # Combine short clips into one sample
claudible voices info NAME       # Show voice sample details
claudible voices record NAME     # Record from mic
claudible voices test NAME       # Test a voice
claudible personas list          # List all personas (built-in + custom)
claudible personas show NAME     # Show persona prompt
claudible personas create NAME   # Create custom persona (opens editor)
claudible personas delete NAME   # Delete custom persona
claudible hooks install          # Install Claude Code hook
claudible hooks uninstall        # Remove hook
claudible daemon install         # Install systemd user service
claudible daemon start/stop      # Start/stop daemon
claudible daemon status/logs     # Check daemon status/logs
claudible install                # Full interactive setup
claudible tui                    # Legacy Textual TUI
```

## Personas
- Built-in: default, jarvis, casual, terse, mission-control, noir, butler, pirate, drill-sergeant
- Custom: ~/.config/claudible/personas/*.txt (plain text system prompts)
- Set active persona in config.toml: `[rephrase] persona = "noir"`
