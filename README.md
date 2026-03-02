# Claudible
This is just a fun little project that I thought I would open up.  I'm still doing some testing, tuning, and updates, but it's quite useful. You have OpenClaw or Claude Remote Control while you are away, but when I'm at my desk I am surrounded by an army of assistants, and Claudible makes me feel a bit like Iron Man, or a manic air traffic controller.  At any time I have 3-4 machines running.  While I'm really focused on one or another task I keep the other ones going with Claudible.  They tell me when they are done and read the relevant information back to me if there is a question or if I need to give them a new task. For fun, I give them different voices and it's easy to add your own voice or others from voice samples.

Personally I'm a huge Dungeon Crawler Carl fan and I use the System AI voice to yell out "New Achievement!" when it completes a big task for me usually with some snarky comment. It does refuse to do work unless I upload a picture of my feet occasionally.  I'll have to look into that.  

Not available for Windows just yet. I currently work for Microsoft so I should have access to one somewhere around here. :)  

Good Luck, Have Fun, Dont Die!

Voice interface for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — (or anything really) hear Claude speak with cloned voices, talk back with push-to-talk, and add personality with AI rephrasing.

Everything runs locally. No cloud APIs, no data leaving your machine.

## Features

- **Text-to-Speech** — Coqui XTTS v2 running locally on your GPU with voice cloning
- **Speech-to-Text** — Push-to-talk via nerd-dictation (VOSK), types directly into your terminal
- **Personality Rephrasing** — Optional Ollama pass that rephrases Claude's output before speaking
- **Smart Filtering** — Only speaks conversational text, skips code blocks and command output
- **Claude Code Integration** — Stop hook automatically speaks every response
- **Voice Management** — Clone from audio files, record your own, or combine short clips
- **12 Built-in Personas** — From a NASA mission controller to a film noir detective
- **Custom Personas** — Drop a text file and create your own character
- **Browser Config UI** — Web-based settings at `localhost:5959/config` (Dashboard, Voice, Rephrase, Personas, STT, Logs)
- **System Tray** — Tray icon with STT/TTS toggles and server status
- **Systemd Daemon** — Runs on login as a user service

## How It Works

```mermaid
graph LR
    A[Claude Code] -->|stop hook| B[Filter]
    B -->|conversational text| C[Rephrase]
    C -->|persona style| D[TTS Engine]
    D -->|audio| E[Speaker]
    F[Microphone] -->|push-to-talk| G[STT]
    G -->|typed text| A
```

When Claude finishes a response, the stop hook fires. The filter strips code blocks, command output, file paths, and technical noise. The rephraser (optional) transforms the text through a persona. The TTS engine speaks it using your chosen voice.

For input, hold Right Ctrl to talk — your speech is transcribed and typed into the terminal.

## Requirements

- Linux
- NVIDIA GPU with 4+ GB VRAM
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [nerd-dictation](https://github.com/ideasman42/nerd-dictation) (for STT)
- [Ollama](https://ollama.ai) (optional, for rephrasing)

## Install

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install claudible globally (uv downloads Python 3.11 automatically)
uv tool install claudible --python 3.11

# Run the interactive setup wizard (installs deps, configures, starts daemon)
claudible install
```

To install from a local clone instead of PyPI:

```bash
git clone https://github.com/JayTitus/claudible.git
uv tool install ./claudible --python 3.11
claudible install
```

## Quick Start

```bash
# Option 1: Run interactively (TTS server + tray icon)
claudible run

# Option 2: Run as a daemon
claudible daemon start

# Install the Claude Code hook so responses are spoken automatically
claudible hooks install

# Test speech manually
claudible speak "Hello, I am claudible."
```

## Personas

Claudible ships with 12 built-in personas that rephrase Claude's output before speaking:

| Persona | Style |
|---------|-------|
| **default** | Natural, conversational |
| **jarvis** | Dry, witty, British AI assistant |
| **casual** | Colleague over coffee |
| **terse** | Telegram-style, stripped to essentials |
| **mission-control** | Apollo-era NASA operator — "All systems nominal" |
| **noir** | 1940s hard-boiled detective — "This case was getting ugly" |
| **butler** | Victorian butler — "Very good, sir" |
| **pirate** | Pirate captain — "Smooth sailing, matey" |
| **drill-sergeant** | Military instructor — "Listen up, recruit!" |
| **announcer** | 1930s radio broadcaster — "Ladies and gentlemen..." |
| **oracle** | Wise, calm, pattern-and-flow |
| **engineer** | Scottish chief engineer — "She cannae take any more!" |

Enable rephrasing in your config:

```toml
[rephrase]
enabled = true
model = "llama3.2:3b"
persona = "noir"
```

### Custom Personas

Create your own persona with a text file:

```bash
# Open your editor to write the system prompt
claudible personas create my-persona

# Or pass the prompt directly
claudible personas create deadpan -p "Rephrase text in a bone-dry, deadpan style. No excitement. Ever. Keep technical accuracy."
```

Custom personas are stored at `~/.config/claudible/personas/*.txt` and override built-in personas with the same name.

```bash
claudible personas list          # List all personas (built-in + custom)
claudible personas show noir     # Show a persona's system prompt
claudible personas delete NAME   # Delete a custom persona
```

## Voices

Voices are stored at `~/.local/share/claudible/voices/`. Each voice is a directory containing a `.wav` reference file.

```bash
# List installed voices
claudible voices list

# Add a voice from a WAV file (validates and resamples to 22050 Hz mono)
claudible voices add myvoice /path/to/sample.wav

# Show voice sample details (duration, sample rate, etc.)
claudible voices info myvoice

# Record a voice from your microphone
claudible voices record myvoice

# Test a voice
claudible voices test myvoice
```

For best results, use 6-15 seconds of clean speech audio at 22050 Hz.

### Combining Short Clips

If you only have short audio clips (2-3 seconds each), combine them into one XTTS-ready sample:

```bash
# Combine clips, picking the longest first until target duration is reached
claudible voices combine hal clip1.wav clip2.mp3 clip3.wav

# Adjust target duration and silence gap between clips
claudible voices combine hal clips/*.wav --duration 12 --gap 0.3
```

Accepts WAV, MP3, FLAC, and OGG files.

## Configuration

Open the browser config UI (requires the TTS server to be running):

```bash
claudible config
```

This opens `http://localhost:5959/config` with a dark-themed dashboard where you can manage voice settings, rephrase options, personas, STT keybinds, noise suppression, and view logs — all from the browser.

Config is stored at `~/.config/claudible/config.toml`:

```toml
[tts]
host = "127.0.0.1"
port = 5959
voice = "default"
language = "en"
speed = 1.0

[stt]
push_to_talk_key = "KEY_RIGHTCTRL"
hold_mode = true
toggle_key = "KEY_SCROLLLOCK"

[rephrase]
enabled = false
api_url = "http://localhost:11434/v1"
model = "llama3.2:3b"
persona = "default"
```

## Keybinds

| Key | Action |
|-----|--------|
| Right Ctrl | Push-to-talk (hold to speak) |
| Scroll Lock | Toggle continuous STT on/off |

Keybinds use evdev and require the user to be in the `input` group:

```bash
sudo usermod -aG input $USER
# Log out and back in for the group change to take effect
```

## Daemon Management

```bash
claudible daemon install    # Copy service file, enable on login
claudible daemon uninstall  # Disable and remove service file
claudible daemon start      # Start the service now
claudible daemon stop       # Stop the service
claudible daemon status     # Show service status
claudible daemon logs       # Follow service logs (Ctrl+C to stop)
```

The `daemon install` command auto-detects the cuDNN library path and writes it into the service file so the GPU works correctly under systemd.

## Building from Source

```bash
git clone https://github.com/JayTitus/claudible.git
cd claudible

# Install in development mode (uv downloads Python 3.11 if needed)
uv venv --python 3.11
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/

# Run the linter
uv run ruff check src/
```

## CLI Reference

```
claudible                           # Status overview
claudible run                       # TTS server + tray icon
claudible server                    # Start TTS server only
claudible ptt                       # Push-to-talk listener only
claudible speak "text"              # Send text to TTS
claudible voices list               # List voices
claudible voices add NAME FILE      # Add voice from WAV
claudible voices combine NAME FILES # Combine short clips into one sample
claudible voices info NAME          # Show voice sample details
claudible voices record NAME        # Record from mic
claudible voices test NAME          # Test a voice
claudible personas list             # List all personas
claudible personas show NAME        # Show persona prompt
claudible personas create NAME      # Create custom persona
claudible personas delete NAME      # Delete custom persona
claudible hooks install             # Install Claude Code hook
claudible hooks uninstall           # Remove hook
claudible hooks status              # Check hook status
claudible daemon install            # Install systemd service
claudible daemon uninstall          # Remove systemd service
claudible daemon start              # Start daemon
claudible daemon stop               # Stop daemon
claudible daemon status             # Show daemon status
claudible daemon logs               # Follow logs
claudible config                    # Open browser config UI
claudible install                   # Interactive setup wizard
claudible tui                       # Legacy Textual TUI
claudible tray                      # System tray icon only
```

## Troubleshooting

**cuDNN not found / CUDA errors under systemd**
The daemon service needs `LD_LIBRARY_PATH` pointing to the nvidia-cudnn package. `claudible daemon install` detects this automatically. If you installed cudnn after the daemon, re-run `claudible daemon install`.

**"Permission denied" on keybinds**
Add your user to the `input` group: `sudo usermod -aG input $USER`, then log out and back in.

**No tray icon**
Make sure you have a system tray (KDE, GNOME with AppIndicator extension, etc.). The `PyGObject` dependency is included for proper GTK/AppIndicator support.

**`transformers` version error**
Coqui TTS 0.22 requires `transformers<4.45`. Re-run `claudible install` to auto-fix, or manually: `uv tool inject claudible transformers==4.44.2`.

**Config UI not loading / 404**
The TTS server must be running for `claudible config` to work. If you updated claudible, restart the daemon (`claudible daemon stop && claudible daemon start`) — an old server process may still be running with the previous code.

**Server not starting**
Check logs with `claudible daemon logs` or run `claudible server` interactively to see errors.

## License

MIT
