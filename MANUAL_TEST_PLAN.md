# Claudible Manual Feature Test Plan

## Prerequisites

### System
- Linux desktop with X11 (KDE/GNOME/etc.)
- RTX GPU with CUDA (for TTS engine)
- PulseAudio or PipeWire audio
- Speakers or headphones connected
- Microphone connected
- User in `input` group (`groups $USER` should show `input`)

### Software
- `claudible` installed via `uv tool install . --python 3.11 --force`
- `nerd-dictation` installed and on PATH
- `xdotool` installed (`sudo apt install xdotool`)
- VOSK model downloaded (at least `small`)
- A terminal emulator (Konsole, gnome-terminal, etc.)
- A web browser

### Optional
- Ollama running locally (`ollama serve`) with a model pulled (e.g. `llama3.2:3b`)
- Podman installed (`sudo apt install podman`) — for container tests
- `nvidia-container-toolkit` configured — for GPU-accelerated container
- Second monitor (for multi-window testing)
- Second terminal open alongside the first

### Test Notation
- **[PASS]** / **[FAIL]** / **[SKIP]** — mark each item
- **[BUG]** — mark with description if unexpected behavior found
- Items marked with (R) require daemon restart after config change

---

## 1. Installation & Setup

### 1.1 Fresh Install

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `uv tool install . --python 3.11 --force` | Installs without errors, binary at `~/.local/bin/claudible` | |
| 2 | `claudible --version` | Prints `claudible, version 0.1.0` | |
| 3 | `claudible` (no args) | Shows status overview: server, model, voice, hook, PID | |
| 4 | `claudible install` | Runs interactive wizard | |
| 5 | Wizard: dependency checks | Reports system deps status (xdotool, cmake, etc.) | |
| 6 | Wizard: bundled voices | Installs voices to `~/.local/share/claudible/voices/` | |
| 7 | Wizard: voice selection | Lists available voices, lets you pick one | |
| 8 | Wizard: PTT key | Asks for push-to-talk key (default: KEY_RIGHTCTRL) | |
| 9 | Wizard: toggle key | Asks for toggle key (default: KEY_SCROLLLOCK) | |
| 10 | Wizard: voice test | Speaks a test phrase through speakers | |
| 11 | Wizard: hook install | Installs Claude Code stop hook | |
| 12 | Wizard: RNNoise | Offers to build RNNoise noise suppression | |
| 13 | Wizard: Ollama container | Detects Podman, offers managed container, pulls models (~4GB) | |
| 14 | Wizard: systemd daemon | Installs user service file | |
| 15 | Wizard: summary | Shows final config summary | |

### 1.2 Re-install Over Existing

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Run wizard again with existing config | Preserves existing settings, doesn't duplicate hooks | |
| 2 | `uv tool install . --python 3.11 --force` over existing install | Clean upgrade, binary replaced | |

---

## 2. Daemon Lifecycle

### 2.1 Start / Stop / Restart

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible start` | Prints "Starting TTS server...", "Launching tray icon (foreground)...", blocks (expected) | |
| 2 | Verify tray icon appears | System tray shows claudible icon (grey = inactive) | |
| 3 | In another terminal: `claudible` | Shows "Process: running (PID xxx)", "Server: running" | |
| 4 | `claudible start` (second instance) | Prints "already running (PID xxx)", exits 0 | |
| 5 | `claudible stop` | Prints "Claudible stopped.", tray icon disappears | |
| 6 | `claudible stop` (when not running) | Prints "Claudible is not running." | |
| 7 | `claudible restart` | Stop + start, server comes back up | |
| 8 | Kill process with `kill <PID>` | Stale PID file cleaned on next `claudible` check | |

### 2.2 Systemd Integration

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `systemctl --user status claudible` | Shows service status | |
| 2 | `systemctl --user start claudible` | Starts daemon, tray icon appears | |
| 3 | `systemctl --user stop claudible` | Stops daemon cleanly | |
| 4 | `systemctl --user restart claudible` | Restart cycle completes | |
| 5 | Log out and log back in | Daemon auto-starts (if enabled) | |

### 2.3 TTS Server Health

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `curl http://127.0.0.1:5959/health` | Returns `{"status":"ok","model_loaded":true}` (after warmup) | |
| 2 | `curl http://127.0.0.1:5959/voices` | Returns JSON array of installed voices | |
| 3 | Open `http://127.0.0.1:5959/config` in browser | Web config UI loads | |

---

## 3. Text-to-Speech

### 3.1 CLI Speech

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible speak "Hello world"` | Speaks "Hello world" through speakers | |
| 2 | `claudible speak "Test" --voice default` | Speaks with default voice | |
| 3 | `claudible speak "Test" --voice nonexistent` | Error or fallback gracefully | |
| 4 | `claudible speak ""` | No crash, no output or graceful error | |
| 5 | `claudible speak "A very long paragraph of text that goes on and on..."` (100+ words) | Speaks the full text without cutting off | |

### 3.2 Voice Management — CLI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible voices list` | Lists all installed voices with filenames | |
| 2 | `claudible voices info default` | Shows duration, sample rate, channels, file size | |
| 3 | `claudible voices test default` | Speaks test phrase with default voice | |
| 4 | `claudible voices test jarvis` (if installed) | Speaks with jarvis voice | |
| 5 | `claudible voices add testvoice /path/to/good.wav` (7s, 22050Hz, mono) | Installs, prints success | |
| 6 | `claudible voices add testvoice /path/to/short.wav` (2s) | ERROR: too short | |
| 7 | `claudible voices add testvoice /path/to/stereo.wav` | Warning about channels, asks to continue | |
| 8 | `claudible voices combine combo clip1.wav clip2.wav clip3.wav` | Combines clips, prints duration + size | |
| 9 | `claudible voices combine combo clip1.wav` (single file) | Still works, processes single file | |
| 10 | `claudible voices record myvoice --duration 5` | Records 5s from mic, saves | |

### 3.3 Voice Management — Web UI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to Voice tab | Shows active voice, active persona, voice list | |
| 2 | Select a voice from dropdown, click Test | Speaks test phrase | |
| 3 | Change speed to 1.5, Save | Toast "saved", subsequent speech is faster | |
| 4 | Change language to "en", Save | No error | |

### 3.4 Voice Studio — Web UI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to Voice Studio tab | Tips card shown, installed voices listed | |
| 2 | Enter voice name "test-studio" | Create button text appears | |
| 3 | Drag-drop a WAV file onto upload zone | File appears in staged list with duration | |
| 4 | Click Browse, select a file | Uploads, appears in staged list | |
| 5 | Upload multiple files | All appear, total duration updates | |
| 6 | Duration bar shows green when >= 6s | Visual indicator correct | |
| 7 | Duration bar shows red when < 6s | Visual indicator correct | |
| 8 | Click X on a staged file | Removed from list | |
| 9 | Click Create Voice (with >= 6s staged) | Processing message, then success toast | |
| 10 | Voice appears in installed list after creation | New voice row visible | |
| 11 | Click Test on installed voice | Plays the voice | |
| 12 | Click Replace on installed voice | Name field populated, button says "Replace Voice" | |
| 13 | Click Delete on installed voice | Confirm dialog, then removed | |
| 14 | Click Clear | Staging cleared | |
| 15 | Create voice with same name as existing | Confirm replace dialog, overwrites | |

---

## 4. Claude Code Hook

### 4.1 Hook Installation — CLI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible hooks install` | Prints "stop hook installed" | |
| 2 | `claudible hooks status` | Prints "hook is installed" | |
| 3 | Verify `~/.claude/settings.json` has the hook entry | JSON has `hooks.Stop` with claudible command | |
| 4 | `claudible hooks install` again | Idempotent, doesn't duplicate | |
| 5 | `claudible hooks uninstall` | Prints "stop hook removed" | |
| 6 | `claudible hooks status` | Prints "NOT installed" | |
| 7 | Re-install after uninstall | Works cleanly | |

### 4.2 Hook Modes — End-to-End

**Setup**: Daemon running, hook installed, Claude Code session open.

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | **Full mode**: Ask Claude a question | Claude's conversational response is spoken aloud | |
| 2 | **Full mode**: Ask Claude to write code | Code-only response is filtered — completion announcement (or silence if mode=none) | |
| 3 | **Full mode**: Ask Claude to edit a file | Mixed response: prose spoken, code skipped | |
| 4 | **Full mode**: Claude asks a question | Question spoken with "?" intonation preserved | |
| 5 | **Full mode**: Claude presents numbered options | IVR format: "Option 1: ..., Option 2: ..." | |
| 6 | Set hook mode to "questions" via web UI → Save (R) | | |
| 7 | **Questions mode**: Claude gives a statement | Not spoken — completion announcement instead | |
| 8 | **Questions mode**: Claude asks a question | Spoken aloud | |
| 9 | **Questions mode**: Claude presents options | Spoken as IVR | |
| 10 | Set hook mode to "completion" via web UI → Save (R) | | |
| 11 | **Completion mode**: Any Claude response | Only completion phrase spoken, never content | |
| 12 | Set hook mode to "off" via web UI → Save (R) | | |
| 13 | **Off mode**: Any Claude response | Total silence | |

### 4.3 Completion Announcements

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Set completion mode to "none" | Code-only responses produce no speech | |
| 2 | Set completion mode to "simple", phrase "Done." | Code-only responses speak "Done." | |
| 3 | Set completion mode to "persona" (Ollama must be running) | Code-only responses speak a persona quip | |
| 4 | Set persona prefix to "New Achievement!" | Quip has prefix prepended | |
| 5 | Test Quip button in web UI | Generates and displays a quip | |
| 6 | Completion mode "persona" with Ollama down | Falls back to simple phrase | |

### 4.4 TTS Mute

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Right-click tray → toggle "Notifications: ON" to OFF | TTS mute flag created, no more speech output | |
| 2 | Claude responds while muted | No speech | |
| 3 | Toggle back to ON | Speech resumes | |
| 4 | Verify `~/.cache/claudible/tts_muted` file created/removed | File presence matches mute state | |

---

## 5. Speech-to-Text

### 5.1 Push-to-Talk (Standalone)

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible ptt` | Prints "PTT listener started" with key name + device count | |
| 2 | Hold Right Ctrl, speak, release | Text typed into focused window while held | |
| 3 | Hold key, say nothing, release | Nothing typed | |
| 4 | Verify text appears at cursor in terminal/editor | Dictated text matches spoken words | |
| 5 | Ctrl+C | PTT listener stops cleanly | |

### 5.2 Toggle Mode (via Tray)

**Setup**: Daemon running with tray icon.

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Press Scroll Lock | Tray icon turns green (active), continuous dictation starts | |
| 2 | Speak normally | Text streams into focused window | |
| 3 | Press Scroll Lock again | Tray icon turns grey (inactive), dictation stops | |
| 4 | Verify no text leaks after toggle off | No spurious typing | |

### 5.3 PTT Mode (via Tray)

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Ensure continuous mode is OFF (grey icon) | | |
| 2 | Hold Right Ctrl | Tray icon turns green | |
| 3 | Speak while holding | Text typed into focused window | |
| 4 | Release Right Ctrl | Tray icon returns to grey | |

### 5.4 STT Menu Toggle

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Right-click tray → click "STT: OFF" | Continuous mode activates, menu shows "STT: ON" | |
| 2 | Right-click tray → click "STT: ON" | Deactivates, menu shows "STT: OFF" | |

### 5.5 Voice Keywords

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | With dictation active, say "submit" | Enter key pressed | |
| 2 | Say "enter" | Enter key pressed | |
| 3 | Say "backspace" | Backspace key pressed | |
| 4 | Say "tab" | Tab key pressed | |
| 5 | Say "escape" | Escape key pressed | |

### 5.6 Option Selection by Voice

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Claude presents numbered options (1, 2, 3) | Options spoken in IVR format | |
| 2 | With dictation active, say "select one" | Digit "1" typed + Enter pressed | |
| 3 | Say "option two" | Digit "2" typed + Enter | |
| 4 | Say "choose three" | Digit "3" typed + Enter | |
| 5 | Say "pick four" | Digit "4" typed + Enter | |
| 6 | Say "number five" | Digit "5" typed + Enter | |

---

## 6. Wake Word System

### 6.1 Basic Wake Word

**Setup**: Enable wake word in web UI, set trigger word (e.g. "jarvis"), toggle continuous dictation ON.

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Enable wake word, set trigger "jarvis", Save (R) | STT restarts, tray shows listening icon (blue/grey) | |
| 2 | Speak random words (not trigger) | Nothing typed — system sleeping | |
| 3 | Say "jarvis" | Tray icon changes to active (green), state = awake | |
| 4 | Say "hello world" | Text typed into terminal | |
| 5 | Wait for timeout (default 15s) | Returns to sleeping, tray icon changes back | |
| 6 | Say "jarvis fix the bug" | Activates, "fix the bug" typed immediately | |

### 6.2 Deactivation Phrases

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Activate with "jarvis" | Awake | |
| 2 | Say "stop listening" | Returns to sleeping | |
| 3 | Activate again, say "go to sleep" | Returns to sleeping | |
| 4 | Activate again, say "never mind" | Returns to sleeping | |

### 6.3 Wake Word + Submit

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Activate with "jarvis" | Awake | |
| 2 | Say "submit" | Enter pressed, returns to sleeping | |

### 6.4 Multi-Slot Wake Words

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Say "jarvis" | Activates slot 1 | |
| 2 | Say "jarvis two" | Activates slot 2 (text goes to slot 2 window) | |
| 3 | Say "jarvis three" | Activates slot 3 | |

### 6.5 Wake Word State in UI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Open STT tab in web UI | Wake word state shows "Sleeping" | |
| 2 | Say trigger word | Badge changes to "Awake" (polls every 5s) | |
| 3 | Wait for timeout | Badge returns to "Sleeping" | |

---

## 7. Window Lock (Process-Based)

### 7.1 Auto-Detection

**Setup**: Daemon running, window lock enabled, watched processes = `claude, codex, gemini`.

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Open terminal A, launch `claude` | Within ~2s, slot 1 assigned with terminal A's window ID | |
| 2 | `claudible windows list` | Shows slot 1 with PID, process "claude", [alive] | |
| 3 | Open terminal B, launch `codex` | Slot 2 assigned with terminal B's window ID | |
| 4 | `claudible windows list` | Shows slot 1 (claude) + slot 2 (codex) | |
| 5 | Kill claude (Ctrl+C or exit) | Slot 1 freed within ~2s | |
| 6 | `claudible windows list` | Only slot 2 remains | |
| 7 | Launch `claude` in terminal C | Gets slot 1 (lowest free) | |
| 8 | Launch `gemini` in terminal D | Gets slot 3 | |

### 7.2 Same Terminal Reuse

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Launch `claude` in terminal A → slot 1 assigned | | |
| 2 | Exit claude, launch `claude` again in same terminal A | Slot 1 updated with new PID, same window ID | |
| 3 | `claudible windows list` | Slot 1 shows new PID, same window | |

### 7.3 Manual Registration (Coexistence)

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible windows register 5` (focus a specific window first) | Slot 5 registered manually | |
| 2 | `claudible windows list` | Slot 5 shows "(manual)" | |
| 3 | Wait several poll cycles | Manual slot 5 is NOT pruned (no pid field) | |
| 4 | Auto-detected slots still work alongside manual | Both types coexist | |

### 7.4 Dictation Target with Window Lock

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Auto-detect claude in terminal A (slot 1) | | |
| 2 | Focus a different window (browser, editor) | | |
| 3 | Activate dictation (toggle or PTT), speak | Text goes to terminal A (not the focused window) | |
| 4 | With wake word: say "jarvis hello" | Text goes to slot 1 terminal | |
| 5 | With wake word: say "jarvis two fix bug" | Text goes to slot 2 terminal | |

### 7.5 tmux / screen

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Open terminal, start tmux, run `claude` inside tmux | Slot assigned to the terminal emulator window | |
| 2 | Split tmux pane, run `codex` in other pane | Same window_id — existing slot updated with new PID | |
| 3 | Dictation text targets the terminal window | Correct | |

### 7.6 Window Lock Disabled

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Uncheck "Enable window lock" in web UI, Save (R) | | |
| 2 | Launch claude | No auto-slot assignment | |
| 3 | `claudible windows list` | Empty or only stale entries | |
| 4 | Dictation types into focused window (default behavior) | | |

### 7.7 Wayland Graceful Degradation

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | On Wayland: launch claude | `find_terminal_window` returns None — process skipped | |
| 2 | No crash, no slot assigned | Degrades gracefully | |
| 3 | Dictation falls back to focused-window behavior | | |

### 7.8 Process Exit During Dictation

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Start dictating to slot 1 (claude) | Text going to terminal A | |
| 2 | Kill claude mid-dictation | Slot 1 pruned within ~2s | |
| 3 | Subsequent text goes to focused window (fallback) | No crash, graceful transition | |

---

## 8. Rephrase / Personas

### 8.1 Persona Management — CLI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible personas list` | All 12 built-in + any custom listed | |
| 2 | `claudible personas show jarvis` | Prints JARVIS prompt | |
| 3 | `claudible personas show default` | Prints default prompt | |
| 4 | `claudible personas create test-persona -p "You are a test."` | Saved to `~/.config/claudible/personas/test-persona.txt` | |
| 5 | `claudible personas list` | Shows `test-persona (custom)` | |
| 6 | `claudible personas show test-persona` | Prints "You are a test." | |
| 7 | `claudible personas delete test-persona` | Deleted, gone from list | |
| 8 | `claudible personas delete nonexistent` | Error: not found | |
| 9 | `claudible personas create test-persona` (no -p flag) | Opens $EDITOR | |

### 8.2 Persona Management — Web UI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to Personas tab | All personas listed as cards | |
| 2 | Active persona has yellow border + "active" badge | Visual indicator correct | |
| 3 | Built-in shows "built-in" badge (green) | Correct | |
| 4 | Custom shows "custom" badge (red) | Correct | |
| 5 | Click persona prompt text | Expands to show full prompt | |
| 6 | Click "Use" on a different persona | Becomes active, toast confirms, page reloads | |
| 7 | Select a different voice in persona dropdown, click "Use" | Voice switches too | |
| 8 | Click "Test" next to voice dropdown | Speaks test audio with that voice | |
| 9 | Create new persona: fill name + prompt, click Create | Appears in list with "custom" badge | |
| 10 | Click "Edit" on custom persona | Textarea appears with current prompt | |
| 11 | Modify prompt, click Save | Toast confirms, prompt updated | |
| 12 | Click "Delete" on custom persona | Confirm dialog, then removed | |
| 13 | Cannot delete built-in personas | No delete button on built-in cards | |

### 8.3 Rephrase — Web UI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to Rephrase tab | Settings populated from config | |
| 2 | Enable rephrase checkbox | Checked | |
| 3 | Set API URL to `http://localhost:11434/v1` | | |
| 4 | Click "Fetch Models" | Dropdown populates with Ollama models (or error toast if down) | |
| 5 | Select a model (e.g. `llama3.2:3b`) | | |
| 6 | Click Save | Toast "Rephrase settings saved" | |
| 7 | Type text in "Test Rephrase" area | | |
| 8 | Click "Test Rephrase" | Rephrased text appears below | |
| 9 | Change persona dropdown, test again | Different rephrase style | |

### 8.4 Rephrase Integration (End-to-End)

**Setup**: Rephrase enabled, Ollama running, persona set to "pirate".

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Ask Claude a question | Response spoken in pirate style | |
| 2 | Switch to "jarvis" persona (via web UI) | Next response in JARVIS style | |
| 3 | Switch to "terse" persona | Response is extremely concise | |
| 4 | Disable rephrase | Response spoken verbatim (no persona) | |

### 8.5 Rephrase Failure Handling

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Enable rephrase, stop Ollama | | |
| 2 | Ask Claude a question | Original text spoken (rephrase fails silently) | |
| 3 | Set API URL to wrong address | Same: original text spoken, no crash | |
| 4 | Set API key to garbage value | Same: graceful fallback | |

---

## 9. Ollama Container

### 9.1 Container CLI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible container status` (no container running) | Shows "not found", managed: no | |
| 2 | `claudible container start` | Starts container on port 11435, waits for ready | |
| 3 | `claudible container status` | Shows "running", healthy: yes, lists models | |
| 4 | `claudible container pull llama3.2:1b` | Pulls model, prints success | |
| 5 | `claudible container pull llama3.2:3b` | Pulls model, prints success | |
| 6 | `claudible container status` | Both models listed | |
| 7 | `claudible container stop` | Container stopped | |
| 8 | `claudible container status` | Shows "not found" | |

### 9.2 Container Enable (Full Setup)

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible container enable` | Sets managed=true + correction.enabled=true in config | |
| 2 | | Starts container if not running | |
| 3 | | Pulls correction model (llama3.2:1b) | |
| 4 | | Pulls rephrase model (llama3.2:3b) | |
| 5 | | Prints "All models ready. STT correction is now enabled." | |
| 6 | `cat ~/.config/claudible/config.toml` | `[container] managed = true`, `[correction] enabled = true` | |
| 7 | `claudible container status` | Running, healthy, both models | |

### 9.3 Container Persistence

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible stop` (daemon) | Claudible stopped, container still running | |
| 2 | `claudible container status` | Still "running" — container persists | |
| 3 | `claudible start` (with managed=true) | Daemon starts, detects existing container, skips startup | |

### 9.4 Container Without Podman

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Uninstall podman, run `claudible container start` | Error: "podman not found" | |
| 2 | Wizard: Step 8 without podman | Skipped, prints install instructions | |

---

## 10. STT Correction

### 10.1 Correction Flow (End-to-End)

**Setup**: Container running with llama3.2:1b, correction enabled, daemon running.

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Enable STT correction in web UI or config.toml | `[correction] enabled = true` | |
| 2 | Activate dictation (PTT or toggle) | | |
| 3 | Speak a phrase with likely VOSK errors | Text typed into terminal | |
| 4 | Check accuracy log: `claudible accuracy tail -n 1` | Shows raw → corrected pair | |
| 5 | If correction changed text: `*` marker, raw ≠ corrected | Correct | |
| 6 | Latency shown (expect 80-300ms on RTX 5090) | Reasonable for 1b model | |

### 10.2 Correction Fallback

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Stop Ollama container: `claudible container stop` | | |
| 2 | Speak with correction enabled | Raw text typed (no correction applied) | |
| 3 | No crash, no delay beyond timeout (1500ms max) | Graceful fallback | |
| 4 | Accuracy log entry shows was_changed=false | Correct | |

### 10.3 Correction Disabled

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Disable correction: `[correction] enabled = false` | | |
| 2 | Speak with dictation active | Raw text typed, no correction call | |
| 3 | No latency overhead | Same speed as before | |
| 4 | No entries added to accuracy log | Correct (or entry with was_changed=false if log_enabled) | |

### 10.4 Correction API (Direct Test)

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `curl -X POST http://127.0.0.1:5959/api/correct -H 'Content-Type: application/json' -d '{"text":"i went too the store"}'` | Returns `{"text":"I went to the store","corrected":true}` | |
| 2 | Same with correction disabled | Returns `{"text":"i went too the store","corrected":false}` | |
| 3 | Empty text: `{"text":""}` | Returns empty text, no error | |

---

## 11. STT Accuracy Tracking

### 11.1 Accuracy CLI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible accuracy report` (no data) | "No correction data yet." | |
| 2 | Enable correction, speak several phrases | Entries accumulate | |
| 3 | `claudible accuracy report` | Shows total, changed count, change rate %, avg/p50/p95 latency | |
| 4 | `claudible accuracy tail -n 5` | Shows last 5 entries: `*` for changed, raw → corrected (latency) | |
| 5 | `claudible accuracy tail -n 1` | Shows only latest entry | |
| 6 | `claudible accuracy clear` | "Accuracy log cleared." | |
| 7 | `claudible accuracy report` | "No correction data yet." again | |

### 11.2 Accuracy Log File

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `cat ~/.cache/claudible/stt_accuracy.jsonl` | One JSON object per line | |
| 2 | Each line has: timestamp, raw, corrected, latency_ms, model, was_changed | All fields present | |
| 3 | Delete the file, speak again | File recreated | |

### 11.3 Accuracy API (Web)

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `curl http://127.0.0.1:5959/api/accuracy/stats` | JSON with total, changed, change_rate, avg/p50/p95 | |
| 2 | `curl http://127.0.0.1:5959/api/accuracy/recent?limit=5` | JSON array of recent entries | |
| 3 | `curl -X DELETE http://127.0.0.1:5959/api/accuracy` | `{"ok":true}`, log cleared | |

---

## 12. Web Config UI

### 12.1 Navigation & Layout

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | `claudible config` | Browser opens `http://127.0.0.1:5959/config` | |
| 2 | Sidebar visible with all tabs: Dashboard, Voice, Studio, Rephrase, Personas, STT, Container, Output, Logs | All present | |
| 3 | Click each tab | Content area switches, no 404s or JS errors | |
| 4 | Active tab highlighted in sidebar (red border) | Visual indicator correct | |
| 5 | Resize browser narrow (< 700px) | Sidebar collapses to horizontal nav | |
| 6 | Toast notifications appear top-right, auto-dismiss in 3s | Correct | |

### 12.2 Dashboard

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Dashboard loads on page open | All cards populated | |
| 2 | "Model loaded" badge: Yes (green) or No (red) | Matches server state | |
| 3 | "Hook installed" badge | Matches `claudible hooks status` | |
| 4 | "Voices: N" | Matches `claudible voices list` count | |
| 5 | Active voice name shown | Matches config | |
| 6 | Rephrase: on/off badge | Matches config | |
| 7 | Persona name shown | Matches config | |
| 8 | Input group badge | Yes if user in input group | |
| 9 | RNNoise badge | Yes if active | |
| 10 | STT correction badge | Yes/No matches config | |
| 11 | Container badge | Running/Off matches state | |
| 12 | Missing deps banner appears if deps missing | Shows apt install command | |
| 13 | Dashboard auto-refreshes every 5s | Values update if state changes | |

### 12.3 STT Settings

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to STT tab | All fields populated from config | |
| 2 | PTT key field shows `KEY_RIGHTCTRL` (or custom) | Matches config | |
| 3 | Toggle key field shows `KEY_SCROLLLOCK` | Matches config | |
| 4 | Hold mode checkbox | Matches config | |
| 5 | VOSK model dropdown | Lists available models with (installed) markers | |
| 6 | Select uninstalled model, click Download | Progress message, then "downloaded" | |
| 7 | Input group badge | Correct status | |
| 8 | Change PTT key to `KEY_F13`, Save | Toast "saved & listener restarted" | |
| 9 | Verify PTT now responds to F13 | Key change took effect | |
| 10 | STT Correction: "Enable STT correction" checkbox | Matches config | |
| 11 | STT Correction: Model field shows `llama3.2:1b` | Matches config | |
| 12 | STT Correction: Timeout field shows `1500` | Matches config | |
| 13 | STT Correction: Log checkbox checked by default | Matches config | |
| 14 | Toggle correction on, Save | Config updated, callback regenerated | |

### 12.4 STT — Window Lock Section

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | "Enable window lock" checkbox | Matches config | |
| 2 | "Watched Processes" field | Shows "claude, codex, gemini" | |
| 3 | "Poll Interval" field | Shows "2.0" | |
| 4 | Window slot list shows registered windows | Slot number, title, process badge, alive/gone badge | |
| 5 | Process name shown as yellow badge on auto-detected slots | Correct for claude/codex/gemini | |
| 6 | "alive" badge (green) for live windows | Correct | |
| 7 | "gone" badge (red) for dead windows | Correct after process exits | |
| 8 | Click X on a slot | Slot removed, toast confirms | |
| 9 | Enter slot number, click "Register Window", switch focus within 3s | Countdown shown, then window captured | |
| 10 | Click "Clear All" | All slots removed | |
| 11 | Change watched processes to "claude, myagent", Save (R) | Config updated, watcher restarts | |
| 12 | Change poll interval to 5.0, Save (R) | Config updated | |
| 13 | Disable window lock, Save (R) | No more auto-detection | |

### 12.5 STT — Wake Word Section

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Enable wake word checkbox, Save (R) | Listener restarts | |
| 2 | Set trigger word "jarvis", Save (R) | Config saved | |
| 3 | Wake word state badge shows "Sleeping" / "Awake" | Updates via 5s poll | |
| 4 | Set sleep timeout to 30, Save (R) | Timeout changes | |
| 5 | Set sleep timeout to 0, Save (R) | Stays awake until deactivation phrase | |
| 6 | Trigger mode "Always listening" | Wake word works in continuous + PTT | |
| 7 | Trigger mode "Push-to-talk only" | Wake word only works during PTT hold | |

### 12.6 STT — Voice Keywords Section

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Default keywords listed: submit→Return, enter→Return, backspace→BackSpace, tab→Tab, escape→Escape | All shown | |
| 2 | Click X to remove a keyword | Removed from list (not saved until Save clicked) | |
| 3 | Add keyword: "undo" → "ctrl+z", click Add | Appears in list | |
| 4 | Click Save | Toast confirms, keywords active | |
| 5 | Test: say "undo" during dictation | Ctrl+Z keystroke sent | |

### 12.7 STT — Noise Suppression Section

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | "RNNoise installed" badge | Correct | |
| 2 | "RNNoise active" badge | Correct | |
| 3 | If not installed: "Install RNNoise" button visible | Correct | |
| 4 | Click Install RNNoise | Building message, then "installed" | |
| 5 | Click "Enable RNNoise Filter" | Active badge turns green | |
| 6 | Click "Disable RNNoise Filter" | Active badge turns red | |

### 12.8 Output Settings

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to Output tab | Hook mode dropdown populated | |
| 2 | Change to each mode (Full, Questions, Completion, Off), Save | Toast confirms each | |
| 3 | IVR Option Detection shows "Active" badge | Always active | |
| 4 | Paste text with numbered options into test area | | |
| 5 | Click "Test Detection" | Detected options listed, IVR text shown | |
| 6 | Paste text without options | "No numbered options detected" | |

### 12.9 Container Tab — Web UI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to Container tab | Status, config, models, accuracy sections visible | |
| 2 | Container status badge shows "not found" or "Running" | Matches `claudible container status` | |
| 3 | Healthy badge: Yes if Ollama responding | Correct | |
| 4 | Port shows configured port (default 11435) | Correct | |
| 5 | Click Start button | "Starting..." message, then status becomes Running | |
| 6 | Click Refresh | Status updates | |
| 7 | Click Stop button | Container stops, badge shows "not found" | |
| 8 | Managed toggle checkbox | Matches config | |
| 9 | GPU toggle checkbox | Matches config | |
| 10 | Correction model field shows `llama3.2:1b` | Matches config | |
| 11 | Rephrase model field shows `llama3.2:3b` | Matches config | |
| 12 | Port field shows `11435` | Matches config | |
| 13 | Change managed to true, Save | Config updated | |
| 14 | Models section shows pulled models | Model names listed | |
| 15 | Enter model name (e.g. `llama3.2:1b`), click Pull | Pull progress, then model appears in list | |
| 16 | STT Accuracy section: stats show totals | Matches `claudible accuracy report` | |
| 17 | Recent corrections: shows raw → corrected pairs | `*` marker for changed entries | |
| 18 | Click Refresh (accuracy) | Stats and recent entries update | |
| 19 | Click Clear Log | Accuracy data cleared | |

### 12.10 Logs

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Navigate to Logs tab | journalctl output shown in monospace viewer | |
| 2 | Click Refresh | Logs reload (scroll to bottom) | |
| 3 | Click Clear | Log viewer emptied | |
| 4 | If journalctl unavailable | "(journalctl not available)" shown | |

---

## 13. Tray Icon States

| # | State | Expected Icon | Menu Text |
|---|-------|--------------|-----------|
| 1 | Idle (no STT) | Grey | "STT: OFF" |
| 2 | Continuous STT ON (no wake word) | Green | "STT: ON" |
| 3 | Continuous STT ON + wake word sleeping | Blue/listening | "STT: Listening for 'jarvis'..." |
| 4 | Continuous STT ON + wake word awake | Green | "STT: Active" |
| 5 | PTT held | Green | (icon only, no menu change) |
| 6 | PTT released | Grey | "STT: OFF" |
| 7 | Server healthy | "Server: running" in menu | |
| 8 | Server down | "Server: stopped" in menu | |
| 9 | Notifications ON | "Notifications: ON" in menu | |
| 10 | Notifications OFF | "Notifications: OFF" in menu | |

---

## 14. Config File Scenarios

### 14.1 config.toml Direct Editing

All config changes below require daemon restart unless otherwise noted.

| # | Scenario | Edit | Expected |
|---|----------|------|----------|
| 1 | Change voice | `[tts] voice = "jarvis"` | Speech uses jarvis voice after restart |
| 2 | Change speed | `[tts] speed = 1.5` | Speech faster |
| 3 | Change port | `[tts] port = 6060` | Server on 6060 after restart |
| 4 | Change PTT key | `[stt] push_to_talk_key = "KEY_F13"` | F13 is PTT after restart |
| 5 | Disable window lock | `[stt] window_lock_enabled = false` | No auto-detection |
| 6 | Change watched processes | `[stt] watched_processes = ["claude", "myagent"]` | Only those scanned |
| 7 | Change poll interval | `[stt] process_watch_interval = 5.0` | Polls every 5s |
| 8 | Enable rephrase | `[rephrase] enabled = true` | Speech rephrased |
| 9 | Change persona | `[rephrase] persona = "pirate"` | Pirate style |
| 10 | Set API key | `[rephrase] api_key = "sk-..."` | Key sent in Authorization header |
| 11 | Set hook mode | `[hook] mode = "questions"` | Only questions spoken |
| 12 | Set completion mode | `[completion] mode = "persona"` | Quip on filtered responses |
| 13 | Custom trigger word | `[rephrase.trigger_words] jarvis = "jarvis"` | Wake word active |
| 14 | Custom keyword | `[dictation.keywords] undo = "ctrl+z"` | Say "undo" → Ctrl+Z |
| 15 | Empty config file | Delete config.toml entirely | All defaults applied |
| 16 | Corrupt config file | Write `{garbage` | Error handled gracefully, defaults used |
| 17 | Missing section | Config with only `[tts]` block | Other sections use defaults |
| 18 | Enable correction | `[correction] enabled = true` | Callback regenerated with correction |
| 19 | Set correction model | `[correction] model = "llama3.2:1b"` | Used for STT correction |
| 20 | Set correction timeout | `[correction] timeout_ms = 2000` | Falls back after 2s |
| 21 | Enable managed container | `[container] managed = true` | Container auto-starts with daemon |
| 22 | Set container port | `[container] port = 11435` | Container binds to this port |

### 14.2 Config Migration

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Old config with `[rephrase] ollama_url = "http://localhost:11434"` | Migrated to `api_url = "http://localhost:11434/v1"` on load |
| 2 | Old config with `[rephrase] model = "Select.blah"` | Model field stripped, uses default |
| 3 | Config with both `ollama_url` and `api_url` | `ollama_url` removed, `api_url` preserved |

### 14.3 Config Persistence Through Web UI

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Change voice speed in web UI, Save | `config.toml` updated with new speed | |
| 2 | Change hook mode in web UI, Save | `config.toml` updated | |
| 3 | Create persona in web UI | `~/.config/claudible/personas/name.txt` created | |
| 4 | Change trigger word in web UI, Save | `config.toml` `[rephrase.trigger_words]` updated | |
| 5 | Change watched processes in web UI, Save | `config.toml` `[stt]` updated with new list | |
| 6 | Toggle STT correction in web UI, Save | `config.toml` `[correction]` updated | |
| 7 | Change container settings in web UI, Save | `config.toml` `[container]` updated | |

---

## 15. Edge Cases & Error Scenarios

### 15.1 Process Watcher Edge Cases

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | Start daemon with no watched processes configured | Watcher doesn't start, no errors | |
| 2 | Start daemon with empty watched_processes list | Same as above | |
| 3 | Two instances of `claude` in different terminals | Slot 1 + slot 2 assigned | |
| 4 | Three instances of `claude` | Slots 1, 2, 3 assigned | |
| 5 | Process exits and restarts rapidly (within 2s poll) | Slot freed and reassigned cleanly | |
| 6 | Process renamed (not matching comm) | Not detected (correct — comm-based) | |
| 7 | Long-running `claude` process | Stays in slot indefinitely (correct) | |
| 8 | 50+ watched processes configured | Scans work (just more `/proc` reads) | |
| 9 | xdotool missing from PATH | `find_terminal_window` returns None, process skipped | |
| 10 | `/proc` permission denied (container?) | `scan_proc_for_names` returns [] | |

### 15.2 Audio Edge Cases

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | Very long Claude response (2000+ chars) | Truncated at 2000 chars + "... truncated." | |
| 2 | Response is entirely Unicode/emoji | TTS handles or fails gracefully | |
| 3 | Multiple rapid responses (queue them) | Spoken sequentially, no overlap | |
| 4 | Audio device disconnected | Error logged, no crash | |

### 15.3 Network Edge Cases

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | TTS server not running, `claudible speak "test"` | Error message printed | |
| 2 | Ollama not running, rephrase enabled | Fallback to original text | |
| 3 | TTS server port already in use | Server fails to bind, error in logs | |
| 4 | Container port 11435 already in use | Container start fails, error message | |
| 5 | STT correction timeout (Ollama slow) | Falls back to raw text after timeout_ms | |
| 6 | Container healthy but model not pulled | Correction fails, falls back to raw | |

### 15.4 File System Edge Cases

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | `~/.config/claudible/` doesn't exist | Created on first run | |
| 2 | `~/.local/share/claudible/voices/` doesn't exist | Created by ensure_dirs() | |
| 3 | `windows.json` corrupt/invalid JSON | Treated as empty state, rewritten | |
| 4 | `wakeword.json` missing | Returns `{"state": "sleeping"}` | |
| 5 | PID file with stale PID | Cleaned up, `is_running()` returns False | |
| 6 | Read-only config directory | Error logged, operations fail gracefully | |
| 7 | `stt_accuracy.jsonl` missing | Created on first correction | |
| 8 | `stt_accuracy.jsonl` corrupt | Partial read, no crash | |
| 9 | `~/.local/share/claudible/ollama/` missing | Created on container start | |

### 15.5 Keyboard/Input Edge Cases

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | Keyboard disconnected during PTT | Device list refreshed, listener continues | |
| 2 | Keyboard reconnected | Detected on next select timeout (~0.5s) | |
| 3 | User NOT in input group | "No keyboard devices found" warning | |
| 4 | Unknown key name in config | Warning logged, listener may not start | |

---

## 16. Multi-Agent Scenario (Full Integration)

This is the highest-level end-to-end test combining all features.

### Setup
- Daemon running with tray icon
- Hook installed
- Rephrase enabled with "jarvis" persona
- Wake word enabled with trigger "jarvis"
- Window lock enabled with watched processes
- Terminal A running `claude`
- Terminal B running `codex` (or second `claude`)

### Test Flow

| # | Step | Expected | Result |
|---|------|----------|--------|
| 1 | Daemon auto-detects both processes | Slot 1 = terminal A, slot 2 = terminal B | |
| 2 | Press Scroll Lock (continuous STT on) | Tray shows listening icon | |
| 3 | Say "jarvis" | Awake, targets slot 1 (terminal A) | |
| 4 | Say "explain the error" | Text typed into terminal A | |
| 5 | Claude in terminal A responds | Response spoken aloud in JARVIS voice | |
| 6 | Say "submit" | Enter pressed in terminal A, returns to sleeping | |
| 7 | Say "jarvis two" | Awake, targets slot 2 (terminal B) | |
| 8 | Say "fix the tests" | Text typed into terminal B | |
| 9 | Exit `claude` in terminal A | Slot 1 freed within ~2s | |
| 10 | Launch new `claude` in terminal C | Slot 1 reassigned to terminal C | |
| 11 | Say "jarvis run the build" | Text goes to slot 1 (terminal C now) | |
| 12 | Toggle Scroll Lock off | STT stops, tray goes grey | |
| 13 | Verify no text leaks, no crashes | Clean state | |

---

## 17. Performance & Stability

| # | Test | Expected | Result |
|---|------|----------|--------|
| 1 | Leave daemon running for 1 hour | No memory leaks, tray responsive | |
| 2 | Rapid toggle on/off (10x in 5s) | No crash, final state correct | |
| 3 | Rapid PTT press/release (10x in 5s) | No overlapping dictation, clean state | |
| 4 | 100 rapid `claudible speak "test"` calls | All queued and spoken, no server crash | |
| 5 | Process watcher with 10+ claude instances | All assigned slots, memory stable | |
| 6 | Web UI open for 30 minutes | No JS errors, polls continue | |
| 7 | Switch tabs rapidly in web UI | No broken state, loaders fire correctly | |
| 8 | Close and reopen browser to config UI | Full reload, state matches server | |

---

## 18. Regression Checklist

After any code change, verify these critical paths:

- [ ] `claudible start` → tray appears → health check passes
- [ ] `claudible speak "hello"` → audio plays
- [ ] Hook fires on Claude response → speech output
- [ ] PTT hold → dictation → release → stops
- [ ] Toggle on → continuous dictation → toggle off
- [ ] Wake word activates → text typed → timeout sleeps
- [ ] Process watcher detects `claude` → slot assigned → exit frees slot
- [ ] Web UI loads all tabs without JS errors
- [ ] Config save from web UI persists to disk
- [ ] Rephrase with persona changes spoken style
- [ ] Window lock routes text to correct terminal
- [ ] `claudible container enable` → starts, pulls models, correction enabled
- [ ] `claudible container status` → shows running + models
- [ ] STT correction: speak → corrected text typed (when enabled)
- [ ] STT correction: falls back to raw when container down
- [ ] `claudible accuracy report` → shows stats
- [ ] Container tab in web UI loads with status + models + accuracy
