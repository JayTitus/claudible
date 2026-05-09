# Claudible Roadmap

## Current State (v0.1)

Claudible is a fully local voice interface for Claude Code and other CLI AI tools. Everything runs on-device with no cloud APIs.

### Text-to-Speech
- Coqui XTTS v2 running on GPU via a persistent FastAPI daemon (localhost:5959)
- Voice cloning from WAV files, microphone recording, or combined short clips
- 15 bundled voices with voice-per-persona mapping
- Configurable speech speed, language, and audio lead-in (for Bluetooth sink wake-up)

### Speech-to-Text
- nerd-dictation wrapping VOSK for offline speech recognition
- Push-to-talk (hold Right Ctrl) and always-listening (toggle Scroll Lock) modes
- Wake word detection with configurable trigger words per persona (e.g., say "Jarvis" to activate)
- Idle timeout auto-deactivation (default 15 seconds)
- Slot routing via wake words ("Jarvis two" targets the second terminal)
- Voice keywords mapped to keystrokes (submit, enter, backspace, tab, escape)
- Option selection by voice ("select 2", "option three")

### Process Watcher and Window Lock
- Daemon thread polls /proc for watched process names (claude, codex, gemini by default)
- Auto-detects CLI tools running in standalone terminal emulators (30+ supported: Konsole, Alacritty, Kitty, WezTerm, etc.)
- Auto-assigns window slots and routes voice input to the correct terminal via xdotool
- STT auto-starts when the first watched process appears, auto-stops when the last exits
- Dead process pruning and same-terminal reuse detection
- Voice registration commands ("register window two")

### Hooks
- Claude Code stop hook reads `last_assistant_message` from stdin JSON
- Four hook modes: full (speak everything), questions (speak only questions), completion (announce task completion), off
- Completion announcements with simple phrase or persona-generated message
- Smart text filtering: strips code blocks, command output, file paths, and technical noise

### Rephrase
- Ollama or any OpenAI-compatible API (Open WebUI, hosted providers)
- 12 built-in personas: default, jarvis, casual, terse, mission-control, noir, butler, pirate, drill-sergeant, announcer, oracle, engineer
- Custom personas stored as plain text system prompts
- Per-persona trigger words, trigger modes (always-listening or PTT-only), and voice assignments

### Audio Pipeline
- RNNoise neural noise suppression via PipeWire filter-chain (built from source, one-click install from UI)
- Configurable RNNoise VAD threshold, grace period, and retroactive audio inclusion
- PipeWire Acoustic Echo Cancellation (WebRTC AEC) to prevent TTS feedback into STT
- Configurable audio lead-in silence for Bluetooth sink wake-up

### Configuration
- TOML config at ~/.config/claudible/config.toml with pydantic models
- Browser-based config UI at localhost:5959/config (six tabs: Dashboard, Voice, Rephrase, Personas, STT, Logs)
- Full CLI for all operations (voices, personas, windows, hooks, install)

### Daemon and Lifecycle
- systemd user service targeting graphical-session.target
- PID-based singleton enforcement
- System tray icon with color-coded STT state (gray/orange/green/red)
- Interactive setup wizard (`claudible install`) handles system packages, Python deps, VOSK model, nerd-dictation, RNNoise, hook installation, and daemon setup

---

## Short-term (v0.2)

### Multi-Agent Output Hooks
- Support output hooks for Gemini CLI and Codex in addition to Claude Code
- Generic webhook endpoint (POST /api/hook/output) for arbitrary tools
- Per-tool hook installer: `claudible hooks install gemini`, `claudible hooks install codex`, `claudible hooks install --all`

### Silero VAD Integration
- ~~Neural voice activity detection (Silero VAD) as a pre-filter before VOSK~~ — **landed for the macOS direct-VOSK path.** Bundled ONNX model + onnxruntime, configurable threshold/grace/pad, and `claudible vad test FILE.wav` for offline tuning.
- Linux integration still pending — requires moving off the nerd-dictation subprocess to a direct sounddevice→VOSK path, since nerd-dictation owns the audio stream.

### VOSK Confidence Filtering
- Expose VOSK per-word confidence scores
- Reject low-confidence recognition results that likely come from background noise
- Configurable confidence threshold in STT settings

### Wayland Support
- Replace xdotool with ydotool or wtype for Wayland compositors
- Auto-detect X11 vs Wayland session and select the correct input method
- Window identification via compositor-specific protocols (wlr-foreign-toplevel, KDE/GNOME extensions)

### Container-Based Install
- Docker/Podman image with CUDA support for the TTS server
- GPU passthrough for XTTS v2 inference
- Simplified deployment without managing Python dependencies and system packages

---

## Medium-term (v0.3)

### Windows Support
- Port from Linux-specific /proc scanning and xdotool to Windows equivalents
- Windows audio pipeline (WASAPI or similar) instead of PipeWire
- Windows service or startup task instead of systemd

### Multi-Mic Beamforming
- Support for USB microphone arrays (ReSpeaker, SEEED, etc.)
- Hardware beamforming to spatially focus on the speaker and reject off-axis noise
- Direction-of-arrival estimation for multi-speaker environments

### Custom Wake Word Training
- Train custom wake words using Picovoice Porcupine, OpenWakeWord, or similar
- Replace VOSK-based trigger word detection with a dedicated always-on wake word engine
- Lower power consumption and fewer false activations than full speech recognition

### Streaming TTS
- Start speaking before the full TTS generation completes
- Sentence-level chunking with overlapping generation and playback
- Lower perceived latency for long responses

### Voice Activity-Based Auto-PTT
- Automatically activate speech capture when voice is detected, deactivate on silence
- Silero VAD-driven (from v0.2) with configurable activation/deactivation thresholds
- No button press or wake word required

### Web UI Voice Management
- Record voice samples directly from the browser config UI
- Preview and test voices with custom text from the UI
- Upload WAV/MP3 files via drag-and-drop

### Plugin System
- Pluggable post-processing pipeline between rephrase and TTS
- Custom filters (profanity, length limiting, translation, summarization)
- Python plugin API with entry point discovery

---

## Long-term Vision

### Cross-Platform
- Full support for Linux, macOS, and Windows
- Platform-native audio pipelines (PipeWire, CoreAudio, WASAPI)
- Platform-native input simulation (xdotool, AppleScript/CGEvent, SendInput)
- Unified installer that adapts to the host OS

### Mobile Companion App
- Control claudible from a phone (start/stop, switch voices, change persona)
- View status and logs remotely
- Use phone microphone as an alternative input device

### Multi-User Support
- Per-user voice and persona profiles
- Speaker identification to automatically switch voices
- Shared daemon with isolated user sessions

### Broader AI Tool Integration
- Hooks for web-based AI agents, IDE copilots (Cursor, Windsurf, Copilot), and custom tools
- Bidirectional voice interface for tools that support streaming input
- Generic adapter framework for any tool that produces text output

---

## Known Limitations

### IDE Integrated Terminals Not Supported
VS Code, JetBrains IDEs, and other editors with built-in terminals cannot be targeted by xdotool. The terminal is an internal widget, not a separate X11 window. Voice input sent to an IDE window goes to whatever element has focus (editor, file explorer, etc.), not the terminal pane. Use standalone terminal emulators for window lock.

### X11 Only (No Wayland Yet)
Window lock and voice input routing depend on xdotool, which is X11-only. Wayland support (ydotool/wtype) is planned for v0.2.

### Linux Only
Currently requires Linux with systemd, PipeWire, and /proc filesystem. Windows and macOS support are long-term goals.

### NVIDIA GPU Required
Coqui XTTS v2 requires an NVIDIA GPU with CUDA and at least 4 GB VRAM. CPU-only inference is not currently supported (it would be too slow for real-time use).

### transformers Version Pin
Coqui TTS 0.22 requires `transformers>=4.44,<4.45` because newer versions removed `BeamSearchScorer`. This pin limits compatibility with other tools that need newer transformers.

### Bluetooth Audio Trade-offs
Bluetooth headsets in HFP/HSP mode (headset profile with mic) drop to 8 kHz CVSD audio quality. The audio lead-in setting helps with sink wake-up latency but adds a small delay to the start of each utterance.

### Single-Language TTS
While XTTS v2 supports multiple languages, the STT pipeline (VOSK model) and wake word detection are configured for a single language at a time.

### nerd-dictation Dependency
STT depends on nerd-dictation as a subprocess wrapper around VOSK. This adds a process boundary and limits control over the recognition pipeline. A tighter VOSK integration could improve latency and enable features like confidence filtering.

---

## Contributing

Claudible is an open source project under the MIT license. Contributions are welcome.

### Getting Started

```bash
git clone https://github.com/JayTitus/claudible.git
cd claudible

uv venv --python 3.11
uv pip install -e ".[dev]"

uv run pytest tests/
uv run ruff check src/
```

### Areas Where Help Is Needed

- **Wayland support** -- ydotool/wtype integration and compositor-specific window identification
- **Windows port** -- process detection, input simulation, audio pipeline, service management
- **Silero VAD integration** -- pre-filtering audio frames before VOSK
- **Streaming TTS** -- sentence-level chunking with overlapping generation and playback
- **Test coverage** -- the test suite is minimal; more unit and integration tests are needed
- **Voice contributions** -- public domain or permissively licensed voice samples (see docs for voice source research)

### Guidelines

- Keep dependencies minimal and prefer local/offline solutions over cloud APIs
- All audio processing and AI inference must run on-device
- Configuration changes should be exposed in both the CLI and the browser config UI
- Use pydantic models for config validation and TOML for persistence
- Follow the existing code style (ruff for linting)

### Reporting Issues

Open an issue on GitHub with:
- Your system info (OS, GPU, CUDA version, Python version)
- Steps to reproduce
- Relevant log output (`journalctl --user -u claudible` or `claudible start` in foreground)
