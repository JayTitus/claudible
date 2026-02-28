# Claudible
This is just a fun little project that I thought I would open up.  I'm still doing some testing, tuning, and updates, but it's quite useful. You have OpenClaw or Claude Remote Control while you are away, but when I'm at my desk I am surrounded by an army of assistants, and Claudible makes me feel a bit like Iron Man, or a manic air traffic controller.  At any time I have 3-4 machines running.  While I'm really focused on one or another task I keep the other ones going with Claudible.  They tell me when they are done and read the relevant information back to me if there is a question or if I need to give them a new task. For fun, I give them different voices and it's easy to add your own voice or others from voice samples.

Personally I'm a huge Dungeon Crawler Carl fan and I use the System AI voice to yell out "New Achievement!" when it completes a big task for me usually with some snarky comment. It does refuse to do work unless I upload a picture of my feet occasionally.  I'll have to look into that.  

Not available for Windows just yet. I currently work for Microsoft so I should have access to one somewhere around here. :)  

Good Luck, Have Fun, Dont Die!

Voice interface for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — (or anything really) hear Claude speak with cloned voices, talk back with push-to-talk, and add personality with AI rephrasing.

## Features

- **Text-to-Speech** — Coqui XTTS v2 running locally on your GPU with voice cloning
- **Speech-to-Text** — Push-to-talk via nerd-dictation (VOSK), types directly into your terminal
- **Personality Rephrasing** — Optional Ollama pass that rephrases Claude's output before speaking
- **Claude Code Integration** — Stop hook automatically speaks every response
- **Voice Management** — Clone from audio files or record your own voice
- **Systemd Services** — Run TTS server and PTT listener as user services

## Requirements

- Linux with PulseAudio/PipeWire
- Python 3.10+
- NVIDIA GPU with 4+ GB VRAM (for XTTS v2)
- [nerd-dictation](https://github.com/ideasman42/nerd-dictation) (for STT)
- [Ollama](https://ollama.ai) (optional, for rephrasing)

## Install

```bash
# Clone
git clone https://github.com/JayTitus/claudible.git
cd claudible

# Install base + TTS
pip install -e ".[tts]"

# Run setup
claudible install

# Add a voice
claudible voices add myvoice /path/to/sample.wav
# Or record one
claudible voices record myvoice

# Start the server
claudible server

# Test it
claudible speak "Hello, I am claudible."
```

## Quick Start

```bash
# 1. Start the TTS server (keep running)
claudible server

# 2. In another terminal, install the Claude Code hook
claudible hooks install

# 3. Use Claude Code normally — responses will be spoken aloud

# 4. (Optional) Start push-to-talk for voice input
claudible ptt
```

## Configuration

Config lives at `~/.config/claudible/config.toml`:

```toml
[tts]
host = "127.0.0.1"
port = 5959
voice = "default"
language = "en"
speed = 1.0

[stt]
push_to_talk_key = "KEY_SCROLLLOCK"
hold_mode = true

[rephrase]
enabled = false
ollama_url = "http://localhost:11434"
model = "llama3.2:3b"
persona = "default"   # default, jarvis, casual, terse
```

## Voices

Voices are stored at `~/.local/share/claudible/voices/`. Each voice is a directory containing a `.wav` reference file:

```
~/.local/share/claudible/voices/
├── myvoice/
│   └── sample.wav
└── jarvis/
    └── jarvis-reference.wav
```

For best results, use 6-15 seconds of clean speech audio at 22050 Hz.

## Systemd Services

```bash
# Copy service files
cp src/claudible/systemd/*.service ~/.config/systemd/user/

# Enable and start
systemctl --user enable --now claudible-tts
systemctl --user enable --now claudible-ptt
```

## License

MIT
