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
├── tui/                # Textual TUI (future)
└── systemd/            # User service units
```

## Key Architecture
- **TTS Server**: Persistent FastAPI daemon on localhost:5959, XTTS v2 on GPU
- **STT**: Wraps nerd-dictation as subprocess, push-to-talk via evdev
- **Rephrase**: Ollama API, transforms text AFTER Claude output but BEFORE TTS
- **Claude Code hook**: Stop hook reads `last_assistant_message` from stdin JSON, fire-and-forget to TTS server
- **Config**: TOML at ~/.config/claudible/config.toml
- **Voices**: ~/.local/share/claudible/voices/ (each voice = subdir with .wav)

## Install extras
- `pip install -e .` — base (client, hooks, PTT)
- `pip install -e ".[tts]"` — TTS server (GPU deps)
- `pip install -e ".[tui]"` — Textual TUI
- `pip install -e ".[dev]"` — dev tools

## Testing
```bash
pytest tests/
```

## CLI
```
claudible                        # Status overview
claudible server                 # Start TTS server
claudible ptt                    # Push-to-talk listener
claudible speak "text"           # Send text to TTS
claudible voices list            # List voices
claudible voices add NAME FILE   # Add voice from WAV
claudible voices record NAME     # Record from mic
claudible voices test NAME       # Test a voice
claudible hooks install          # Install Claude Code hook
claudible hooks uninstall        # Remove hook
claudible install                # Full interactive setup
```
