"""Textual TUI for claudible configuration and control."""

from __future__ import annotations

import asyncio
import grp
import os
import subprocess
import sys
from pathlib import Path

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    Switch,
)

from claudible.config import Config
from claudible.paths import VOICES_DIR
from claudible.rephrase.personas import get_persona_prompt, list_personas
from claudible.tts.client import TTSClient
from claudible.tts.voices import list_voices


def _select_is_blank(select: Select) -> bool:
    """Check if a Select widget has no value (handles both old and new Textual)."""
    try:
        return select.value is Select.BLANK
    except AttributeError:
        return select.value is Select.NULL


APP_CSS = """
Screen {
    layout: horizontal;
    background: $surface;
}

/* ── Sidebar ─────────────────────────────────────────────── */

#sidebar {
    width: 24;
    dock: left;
    background: $panel;
    border-right: thick $primary-background;
    padding: 1 0;
}

#sidebar-title {
    text-align: center;
    text-style: bold;
    color: $accent;
    padding: 0 1 1 1;
}

.nav-btn {
    width: 100%;
    margin: 0 1;
    min-width: 20;
}

.nav-btn.nav-active {
    background: $accent;
    color: $text;
    text-style: bold;
}

/* ── Content area ────────────────────────────────────────── */

#content-area {
    width: 1fr;
    height: 100%;
}

#status-bar {
    dock: top;
    height: 1;
    background: $primary-background;
    color: $text-muted;
    padding: 0 2;
}

ContentSwitcher {
    width: 100%;
    height: 1fr;
}

.panel {
    padding: 1 2;
}

/* ── Cards ───────────────────────────────────────────────── */

.card {
    background: $panel;
    border: round $primary-background;
    padding: 1 2;
    margin: 1 0;
    height: auto;
}

.card-title {
    text-style: bold;
    color: $accent;
    margin: 0 0 1 0;
}

/* ── Fields ──────────────────────────────────────────────── */

.field-row {
    layout: horizontal;
    height: 3;
    align: left middle;
}

.field-label {
    width: 20;
    content-align: right middle;
    padding: 0 1;
    color: $text-muted;
}

.field-input {
    width: 1fr;
}

.help-text {
    color: $text-disabled;
    margin: 0 0 0 21;
    height: auto;
}

/* ── Buttons ─────────────────────────────────────────────── */

.btn-row {
    layout: horizontal;
    height: 3;
    margin: 1 0 0 0;
}

.btn-row Button {
    margin: 0 1 0 0;
}

.btn-inline {
    margin: 0 0 0 1;
    min-width: 10;
}

/* ── Specific widgets ────────────────────────────────────── */

.explainer {
    color: $text-muted;
    margin: 0 0 1 0;
}

#voice-info {
    color: $text-muted;
    margin: 0 0 0 21;
    height: auto;
}

#ollama-status {
    margin: 0 0 0 21;
    height: auto;
}

#rephrase-output {
    height: 6;
    border: round $primary-background;
    padding: 0 1;
    margin: 1 0;
    background: $surface;
}

#persona-preview {
    margin: 0 0 0 21;
    height: auto;
    max-height: 4;
}

#log-viewer {
    height: 1fr;
    border: round $primary-background;
    background: $surface;
}

#stt-group-status {
    margin: 0 0 0 21;
    height: auto;
}

#rnnoise-status {
    margin: 0 0 0 21;
    height: auto;
}

"""


class ClaudibleApp(App):
    """Claudible configuration and control TUI."""

    TITLE = "Claudible"
    CSS = APP_CSS

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("1", "nav('dashboard')", "Dashboard"),
        ("2", "nav('voice')", "Voice"),
        ("3", "nav('rephrase')", "Rephrase"),
        ("4", "nav('stt')", "STT"),
        ("5", "nav('logs')", "Logs"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = Config.load()
        self.client = TTSClient(
            base_url=f"http://{self.config.tts.host}:{self.config.tts.port}"
        )

    # ── Layout ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="sidebar"):
            yield Static("CLAUDIBLE", id="sidebar-title")
            yield Button("1 Dashboard", id="nav-dashboard", classes="nav-btn nav-active")
            yield Button("2 Voice", id="nav-voice", classes="nav-btn")
            yield Button("3 Rephrase", id="nav-rephrase", classes="nav-btn")
            yield Button("4 Speech Input", id="nav-stt", classes="nav-btn")
            yield Button("5 Logs", id="nav-logs", classes="nav-btn")

        with Vertical(id="content-area"):
            yield Static("", id="status-bar")
            with ContentSwitcher(initial="dashboard"):
                yield from self._wrap_panel("dashboard", self._compose_dashboard)
                yield from self._wrap_panel("voice", self._compose_voice)
                yield from self._wrap_panel("rephrase", self._compose_rephrase)
                yield from self._wrap_panel("stt", self._compose_stt)
                yield from self._wrap_panel("logs", self._compose_logs)

        yield Footer()

    def _wrap_panel(self, panel_id: str, composer) -> ComposeResult:
        """Wrap a panel composer in a VerticalScroll with the right ID."""
        with VerticalScroll(id=panel_id, classes="panel"):
            yield from composer()

    # ── Dashboard ─────────────────────────────────────────────────────────

    def _compose_dashboard(self) -> ComposeResult:
        with Vertical(classes="card"):
            yield Static("Server Status", classes="card-title")
            yield Static("[dim]Checking...[/]", id="dash-server-status")
            yield Static(
                "[dim]The TTS server synthesizes speech from text. "
                "It must be running for voice output to work.[/]",
                classes="help-text",
            )
            with Horizontal(classes="btn-row"):
                yield Button("Start Server", id="btn-server-start", variant="success")
                yield Button("Stop Server", id="btn-server-stop", variant="error")

        with Vertical(classes="card"):
            yield Static("Current Configuration", classes="card-title")
            yield Static("", id="dash-voice")
            yield Static("", id="dash-persona")
            yield Static("", id="dash-voices-count")
            yield Static("", id="dash-hook-status")
            yield Static("", id="dash-server-addr")

    # ── Voice & Output ────────────────────────────────────────────────────

    def _compose_voice(self) -> ComposeResult:
        with Vertical(classes="card"):
            yield Static("Voice Selection", classes="card-title")
            yield Static(
                "[dim]Choose which voice the TTS engine clones. "
                "Each voice is a WAV sample in your voices directory.[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Voice", classes="field-label")
                yield Select(
                    [], id="voice-select", classes="field-input", allow_blank=True
                )
                yield Button(
                    "Test", id="btn-voice-test", variant="primary", classes="btn-inline"
                )
            yield Static("[dim]Select a voice to see details[/]", id="voice-info")
            with Horizontal(classes="btn-row"):
                yield Button("Refresh", id="btn-voices-refresh")

        with Vertical(classes="card"):
            yield Static("Output Settings", classes="card-title")
            with Horizontal(classes="field-row"):
                yield Label("Speed", classes="field-label")
                yield Input(
                    value=str(self.config.tts.speed),
                    id="cfg-tts-speed",
                    classes="field-input",
                )
            yield Static(
                "[dim]Playback speed multiplier (0.5 = slow, 1.0 = normal, 2.0 = fast)[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Language", classes="field-label")
                yield Input(
                    value=self.config.tts.language,
                    id="cfg-tts-lang",
                    classes="field-input",
                )
            yield Static(
                "[dim]ISO language code for TTS synthesis (en, de, fr, es, etc.)[/]",
                classes="help-text",
            )

        with Vertical(classes="card"):
            yield Static("Voices Directory", classes="card-title")
            yield Static(
                f"[dim]Where voice samples are stored. Leave blank for default: {VOICES_DIR}[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Path", classes="field-label")
                yield Input(
                    value=self.config.tts.voices_dir,
                    placeholder=str(VOICES_DIR),
                    id="cfg-voices-dir",
                    classes="field-input",
                )

        with Horizontal(classes="btn-row"):
            yield Button("Save Voice Settings", id="btn-voice-save", variant="primary")

    # ── Rephrase & Personas ───────────────────────────────────────────────

    def _compose_rephrase(self) -> ComposeResult:
        with Vertical(classes="card"):
            yield Static("Rephrase Engine", classes="card-title")
            yield Static(
                "[dim]Rephrase runs Claude's text output through an LLM "
                "to add personality before speaking. For example, the 'pirate' persona "
                "turns 'File saved' into 'The treasure map be stowed, captain!'[/]",
                classes="explainer",
            )
            yield Static(
                "[dim]Works with any OpenAI-compatible API: Ollama, Open WebUI, LiteLLM, etc.[/]",
                classes="explainer",
            )
            with Horizontal(classes="field-row"):
                yield Label("Enabled", classes="field-label")
                yield Switch(
                    value=self.config.rephrase.enabled, id="cfg-rephrase-enabled"
                )
            yield Static(
                "[dim]When off, Claude's output is spoken directly without rephrasing[/]",
                classes="help-text",
            )

        with Vertical(classes="card", id="rephrase-settings"):
            yield Static("API Connection", classes="card-title")
            yield Static("", id="ollama-status")
            with Horizontal(classes="field-row"):
                yield Label("API URL", classes="field-label")
                yield Input(
                    value=self.config.rephrase.api_url,
                    id="cfg-rephrase-url",
                    classes="field-input",
                )
                yield Button(
                    "Test", id="btn-ollama-test", variant="default", classes="btn-inline"
                )
            yield Static(
                "[dim]OpenAI-compatible base URL. Examples:\n"
                "  Ollama:      http://localhost:11434/v1\n"
                "  Open WebUI:  http://your-host:3000/api\n"
                "  LiteLLM:    http://localhost:4000/v1[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("API Key", classes="field-label")
                yield Input(
                    value=self.config.rephrase.api_key,
                    id="cfg-rephrase-api-key",
                    classes="field-input",
                    password=True,
                    placeholder="optional — needed for Open WebUI / hosted APIs",
                )
            yield Static(
                "[dim]Leave blank for local Ollama (no auth needed)[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Model", classes="field-label")
                yield Select(
                    [], id="cfg-rephrase-model", classes="field-input", allow_blank=True
                )
                yield Button(
                    "Refresh", id="btn-ollama-refresh-models", classes="btn-inline"
                )
            yield Static(
                "[dim]Model for rephrasing. Smaller (3b) = faster, larger (7b+) = more creative.[/]",
                classes="help-text",
            )

        with Vertical(classes="card", id="persona-settings"):
            yield Static("Persona", classes="card-title")
            yield Static(
                "[dim]Personas define the personality style for rephrasing. "
                "Custom personas can be added as .txt files in ~/.config/claudible/personas/[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Active Persona", classes="field-label")
                yield Select(
                    [], id="persona-select", classes="field-input", allow_blank=True
                )
            yield Static("", id="persona-preview")

        with Vertical(classes="card", id="rephrase-test-card"):
            yield Static("Test Rephrase", classes="card-title")
            yield Static(
                "[dim]Type some text and hit Test to see how the current persona rephrases it. "
                "Requires the API server running with the selected model.[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Input", classes="field-label")
                yield Input(
                    placeholder="Type text to rephrase...",
                    id="rephrase-test-input",
                    classes="field-input",
                )
                yield Button(
                    "Test", id="btn-rephrase-test", variant="primary", classes="btn-inline"
                )
            yield Static("[dim]Output will appear here[/]", id="rephrase-output")

        with Horizontal(classes="btn-row"):
            yield Button("Save Rephrase Settings", id="btn-rephrase-save", variant="primary")

    # ── Speech Input (STT) ────────────────────────────────────────────────

    def _compose_stt(self) -> ComposeResult:
        ptt_keys = [
            ("KEY_RIGHTCTRL — Right Ctrl", "KEY_RIGHTCTRL"),
            ("KEY_SCROLLLOCK — Scroll Lock", "KEY_SCROLLLOCK"),
            ("KEY_PAUSE — Pause/Break", "KEY_PAUSE"),
            ("KEY_F13", "KEY_F13"),
            ("KEY_F24", "KEY_F24"),
        ]
        toggle_keys = [
            ("KEY_SCROLLLOCK — Scroll Lock", "KEY_SCROLLLOCK"),
            ("KEY_PAUSE — Pause/Break", "KEY_PAUSE"),
            ("KEY_F13", "KEY_F13"),
            ("KEY_F24", "KEY_F24"),
        ]

        with Vertical(classes="card"):
            yield Static("Push-to-Talk Keys", classes="card-title")
            yield Static(
                "[dim]These keys are captured globally via evdev (no window focus needed). "
                "Your user must be in the 'input' group for this to work.[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("PTT Key", classes="field-label")
                yield Select(
                    options=ptt_keys,
                    value=self.config.stt.push_to_talk_key,
                    id="cfg-stt-ptt-key",
                    allow_blank=False,
                )
            yield Static(
                "[dim]Hold this key to record speech (push-to-talk mode)[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Toggle Key", classes="field-label")
                yield Select(
                    options=toggle_keys,
                    value=self.config.stt.toggle_key,
                    id="cfg-stt-toggle-key",
                    allow_blank=False,
                )
            yield Static(
                "[dim]Press once to start continuous listening, press again to stop[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Hold Mode", classes="field-label")
                yield Switch(value=self.config.stt.hold_mode, id="cfg-stt-hold")
            yield Static(
                "[dim]On: hold PTT key to talk. Off: press once to start, press again to stop[/]",
                classes="help-text",
            )

        with Vertical(classes="card"):
            yield Static("VOSK Speech Recognition", classes="card-title")
            yield Static(
                "[dim]VOSK provides offline speech-to-text via nerd-dictation. "
                "Models are stored in ~/.local/share/vosk/[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Model", classes="field-label")
                yield Input(
                    value=self.config.stt.vosk_model,
                    id="cfg-stt-vosk",
                    classes="field-input",
                    placeholder="e.g. small",
                )
            yield Static(
                "[dim]Model directory name (e.g. 'small', 'large'). "
                "Download from https://alphacephei.com/vosk/models[/]",
                classes="help-text",
            )
            yield Static("", id="stt-group-status")

        with Vertical(classes="card"):
            yield Static("Noise Suppression", classes="card-title")
            yield Static(
                "[dim]Uses RNNoise neural network to filter background noise from your mic "
                "via PipeWire. Recommended when not using a headset.[/]",
                classes="help-text",
            )
            with Horizontal(classes="field-row"):
                yield Label("Enabled", classes="field-label")
                yield Switch(
                    value=self.config.stt.noise_suppression,
                    id="cfg-stt-noise-suppression",
                )
            yield Static("", id="rnnoise-status")

        with Horizontal(classes="btn-row"):
            yield Button("Save STT Settings", id="btn-stt-save", variant="primary")

    # ── Logs ──────────────────────────────────────────────────────────────

    def _compose_logs(self) -> ComposeResult:
        with Vertical(classes="card"):
            yield Static("Service Logs", classes="card-title")
            yield Static(
                "[dim]Live logs from the claudible systemd service. "
                "Shows TTS server activity, errors, and speech events.[/]",
                classes="help-text",
            )
            with Horizontal(classes="btn-row"):
                yield Button("Refresh", id="btn-logs-refresh")
                yield Button("Clear", id="btn-logs-clear")
        yield RichLog(highlight=True, markup=True, id="log-viewer")

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._refresh_server_status()
        self._populate_voices()
        self._populate_personas()
        self._detect_ollama()
        self._update_dashboard_info()
        self._update_rephrase_visibility()
        self._check_input_group()
        self._check_rnnoise_status()
        self._load_logs()
        self.set_interval(5.0, self._refresh_server_status)

    # ── Navigation ────────────────────────────────────────────────────────

    def action_nav(self, panel: str) -> None:
        self._switch_panel(panel)

    def _switch_panel(self, panel: str) -> None:
        self.query_one(ContentSwitcher).current = panel
        for btn in self.query(".nav-btn"):
            btn.remove_class("nav-active")
        try:
            self.query_one(f"#nav-{panel}").add_class("nav-active")
        except Exception:
            pass

    # ── Event handlers ────────────────────────────────────────────────────

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        if btn_id.startswith("nav-"):
            self._switch_panel(btn_id.removeprefix("nav-"))
            return

        handlers: dict[str, object] = {
            "btn-server-start": self._start_server,
            "btn-server-stop": self._stop_server,
            "btn-voice-test": self._test_voice,
            "btn-voices-refresh": self._populate_voices,
            "btn-voice-save": self._save_voice_config,
            "btn-ollama-test": self._detect_ollama,
            "btn-ollama-refresh-models": self._detect_ollama,
            "btn-rephrase-test": self._do_rephrase_test,
            "btn-rephrase-save": self._save_rephrase_config,
            "btn-stt-save": self._save_stt_config,
            "btn-logs-refresh": self._load_logs,
            "btn-logs-clear": self._clear_logs,
        }
        handler = handlers.get(btn_id)
        if handler:
            result = handler()
            if asyncio.iscoroutine(result):
                await result

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "voice-select":
            self._update_voice_info()
        elif event.select.id == "persona-select":
            self._update_persona_preview()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "cfg-rephrase-enabled":
            self._update_rephrase_visibility()
        elif event.switch.id == "cfg-stt-noise-suppression":
            self._toggle_noise_suppression(event.value)

    # ── Server ────────────────────────────────────────────────────────────

    @work(exclusive=True, group="server-status")
    async def _refresh_server_status(self) -> None:
        try:
            healthy = await self.client.health()
        except Exception:
            healthy = False

        addr = f"{self.config.tts.host}:{self.config.tts.port}"
        try:
            w = self.query_one("#dash-server-status", Static)
            if healthy:
                w.update(f"[green bold]● RUNNING[/]  on {addr}")
            else:
                w.update("[red bold]● STOPPED[/]")
        except Exception:
            pass

        try:
            bar = self.query_one("#status-bar", Static)
            if healthy:
                bar.update(f" [green]●[/] Server running on {addr}")
            else:
                bar.update(" [red]●[/] Server stopped")
        except Exception:
            pass

    async def _start_server(self) -> None:
        self._set_status("Starting server...")
        subprocess.Popen(
            [sys.executable, "-m", "claudible.cli", "server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        await asyncio.sleep(2)
        self._refresh_server_status()

    async def _stop_server(self) -> None:
        self._set_status("Stopping server...")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{self.client.base_url}/shutdown")
            self._set_status("Server stopped")
        except Exception:
            self._set_status("Failed to stop server")
        await asyncio.sleep(1)
        self._refresh_server_status()

    # ── Voice ─────────────────────────────────────────────────────────────

    def _voices_dir_override(self) -> str | None:
        d = self.config.tts.voices_dir.strip()
        return d if d else None

    def _populate_voices(self) -> None:
        voices = list_voices(voices_dir=self._voices_dir_override())
        voice_select = self.query_one("#voice-select", Select)
        options = [(v.name, v.name) for v in voices]
        voice_select.set_options(options)
        if options:
            current = self.config.tts.voice
            if any(name == current for name, _ in options):
                voice_select.value = current
            else:
                voice_select.value = options[0][1]
        self._update_voice_info()
        try:
            self.query_one("#dash-voices-count", Static).update(
                f"[dim]Voices:[/] [bold]{len(voices)}[/] installed"
            )
        except Exception:
            pass

    def _update_voice_info(self) -> None:
        select = self.query_one("#voice-select", Select)
        info_w = self.query_one("#voice-info", Static)
        if _select_is_blank(select):
            info_w.update("[dim]No voice selected[/]")
            return
        try:
            from claudible.tts.voices import get_voice_info

            info = get_voice_info(str(select.value), voices_dir=self._voices_dir_override())
            info_w.update(
                f"Duration: {info['duration']}s  |  "
                f"Rate: {info['sample_rate']} Hz  |  "
                f"Size: {info['file_size_kb']} KB"
            )
        except Exception as e:
            info_w.update(f"[dim]Could not load voice info: {e}[/]")

    async def _test_voice(self) -> None:
        select = self.query_one("#voice-select", Select)
        if _select_is_blank(select):
            self._set_status("No voice selected")
            return
        name = str(select.value)
        self._set_status(f"Testing voice: {name}...")
        ok = await self.client.speak(
            "Hello, this is a voice test from claudible.", voice=name
        )
        self._set_status(
            f"Voice test sent: {name}" if ok else "Voice test failed — is the server running?"
        )

    def _save_voice_config(self) -> None:
        try:
            select = self.query_one("#voice-select", Select)
            if not _select_is_blank(select):
                self.config.tts.voice = str(select.value)
            speed_str = self.query_one("#cfg-tts-speed", Input).value.strip()
            self.config.tts.speed = float(speed_str) if speed_str else 1.0
            self.config.tts.language = self.query_one("#cfg-tts-lang", Input).value.strip() or "en"
            self.config.tts.voices_dir = self.query_one("#cfg-voices-dir", Input).value.strip()
            self.config.save()
            self._set_status("Voice settings saved")
            self._populate_voices()
            self._update_dashboard_info()
        except Exception as e:
            self._set_status(f"Save failed: {e}")

    # ── Rephrase ──────────────────────────────────────────────────────────

    def _populate_personas(self) -> None:
        personas = list_personas()
        select = self.query_one("#persona-select", Select)
        options = [(p, p) for p in personas]
        select.set_options(options)
        current = self.config.rephrase.persona
        if current in personas:
            select.value = current
        elif options:
            select.value = options[0][1]
        self._update_persona_preview()

    def _update_persona_preview(self) -> None:
        select = self.query_one("#persona-select", Select)
        preview = self.query_one("#persona-preview", Static)
        if _select_is_blank(select):
            preview.update("")
            return
        prompt = get_persona_prompt(str(select.value))
        if len(prompt) > 250:
            prompt = prompt[:250] + "..."
        preview.update(f"[dim italic]{prompt}[/]")

    def _update_rephrase_visibility(self) -> None:
        enabled = self.query_one("#cfg-rephrase-enabled", Switch).value
        for cid in ("#rephrase-settings", "#persona-settings", "#rephrase-test-card"):
            try:
                self.query_one(cid).display = enabled
            except Exception:
                pass

    @work(exclusive=True, group="ollama-detect")
    async def _detect_ollama(self) -> None:
        status_w = self.query_one("#ollama-status", Static)
        model_select = self.query_one("#cfg-rephrase-model", Select)
        status_w.update("[dim]Connecting to API...[/]")

        # Temporarily apply UI values to config for list_models
        from claudible.rephrase.ollama import list_models

        orig_url = self.config.rephrase.api_url
        orig_key = self.config.rephrase.api_key
        self.config.rephrase.api_url = self.query_one("#cfg-rephrase-url", Input).value.strip()
        self.config.rephrase.api_key = self.query_one("#cfg-rephrase-api-key", Input).value.strip()

        try:
            models = await list_models(config=self.config)

            if models:
                options = []
                for m in models:
                    model_id = m.get("id", "unknown")
                    options.append((model_id, model_id))
                model_select.set_options(options)

                current = self.config.rephrase.model
                model_ids = [mid for _, mid in options]
                if current in model_ids:
                    model_select.value = current
                elif options:
                    model_select.value = options[0][1]

                status_w.update(
                    f"[green]● Connected[/] — {len(models)} model{'s' if len(models) != 1 else ''} available"
                )
            else:
                model_select.set_options([])
                status_w.update("[yellow]● Connected but no models found[/]")
        except httpx.ConnectError:
            model_select.set_options([])
            status_w.update(
                "[red]● Cannot connect[/] — check the API URL and that the server is running"
            )
        except Exception as e:
            model_select.set_options([])
            status_w.update(f"[red]● Error:[/] {e}")
        finally:
            self.config.rephrase.api_url = orig_url
            self.config.rephrase.api_key = orig_key

    @work(exclusive=True, group="rephrase-test")
    async def _do_rephrase_test(self) -> None:
        text = self.query_one("#rephrase-test-input", Input).value.strip()
        if not text:
            self._set_status("Enter text to rephrase first")
            return

        output = self.query_one("#rephrase-output", Static)
        output.update("[dim]Sending to API...[/]")

        persona_select = self.query_one("#persona-select", Select)
        persona = str(persona_select.value) if not _select_is_blank(persona_select) else "default"

        orig_persona = self.config.rephrase.persona
        orig_enabled = self.config.rephrase.enabled
        self.config.rephrase.persona = persona
        self.config.rephrase.enabled = True

        try:
            from claudible.rephrase.ollama import rephrase

            result = await rephrase(text, config=self.config)
            output.update(result)
            self._set_status("Rephrase complete")
        except Exception as e:
            output.update(f"[red]Error: {e}[/]")
            self._set_status("Rephrase failed")
        finally:
            self.config.rephrase.persona = orig_persona
            self.config.rephrase.enabled = orig_enabled

    def _save_rephrase_config(self) -> None:
        try:
            self.config.rephrase.enabled = self.query_one(
                "#cfg-rephrase-enabled", Switch
            ).value
            self.config.rephrase.api_url = (
                self.query_one("#cfg-rephrase-url", Input).value.strip()
            )
            self.config.rephrase.api_key = (
                self.query_one("#cfg-rephrase-api-key", Input).value.strip()
            )
            model_select = self.query_one("#cfg-rephrase-model", Select)
            if not _select_is_blank(model_select):
                self.config.rephrase.model = str(model_select.value)
            persona_select = self.query_one("#persona-select", Select)
            if not _select_is_blank(persona_select):
                self.config.rephrase.persona = str(persona_select.value)
            self.config.save()
            self._set_status("Rephrase settings saved")
            self._update_dashboard_info()
        except Exception as e:
            self._set_status(f"Save failed: {e}")

    # ── STT ───────────────────────────────────────────────────────────────

    def _check_input_group(self) -> None:
        w = self.query_one("#stt-group-status", Static)
        try:
            username = os.getlogin()
            user_groups = [g.gr_name for g in grp.getgrall() if username in g.gr_mem]
            if "input" in user_groups:
                w.update("[green]●[/] User in 'input' group — keybinds will work")
            else:
                w.update(
                    "[yellow]● Warning:[/] User not in 'input' group — "
                    "evdev keybinds won't work.\n"
                    "Run: [bold]sudo usermod -aG input $USER[/] then log out and back in."
                )
        except Exception:
            w.update("[dim]Could not check group membership[/]")

    def _check_rnnoise_status(self) -> None:
        w = self.query_one("#rnnoise-status", Static)
        try:
            from claudible.stt.noise import is_rnnoise_active, is_rnnoise_installed

            installed = is_rnnoise_installed()
            parts = []
            if installed:
                parts.append("[green]● Plugin installed[/]")
            else:
                parts.append("[yellow]● Plugin not installed[/]")

            active = is_rnnoise_active()
            if active:
                parts.append("[green]● Filter active[/]")
            elif self.config.stt.noise_suppression and installed:
                parts.append("[yellow]● Filter not active[/]")

            if not installed:
                parts.append("[dim](run: claudible install)[/]")

            w.update("  ".join(parts))
        except Exception as e:
            w.update(f"[dim]Could not check RNNoise status: {e}[/]")

    @work(exclusive=True, group="rnnoise-toggle")
    async def _toggle_noise_suppression(self, enabled: bool) -> None:
        from claudible.stt.noise import (
            disable_rnnoise,
            enable_rnnoise,
            is_rnnoise_installed,
        )

        if enabled and not is_rnnoise_installed():
            self._set_status("RNNoise not installed — run: claudible install")
            try:
                self.query_one("#cfg-stt-noise-suppression", Switch).value = False
            except Exception:
                pass
            return

        self._set_status("Enabling noise suppression..." if enabled else "Disabling noise suppression...")
        if enabled:
            ok = await asyncio.to_thread(enable_rnnoise)
        else:
            ok = await asyncio.to_thread(disable_rnnoise)

        if ok:
            self._set_status("Noise suppression " + ("enabled" if enabled else "disabled"))
        else:
            self._set_status("Failed to " + ("enable" if enabled else "disable") + " noise suppression")

        self._check_rnnoise_status()

    def _save_stt_config(self) -> None:
        try:
            ptt = self.query_one("#cfg-stt-ptt-key", Select)
            if not _select_is_blank(ptt):
                self.config.stt.push_to_talk_key = str(ptt.value)
            toggle = self.query_one("#cfg-stt-toggle-key", Select)
            if not _select_is_blank(toggle):
                self.config.stt.toggle_key = str(toggle.value)
            self.config.stt.hold_mode = self.query_one("#cfg-stt-hold", Switch).value
            self.config.stt.vosk_model = (
                self.query_one("#cfg-stt-vosk", Input).value.strip() or "small"
            )
            self.config.stt.noise_suppression = self.query_one(
                "#cfg-stt-noise-suppression", Switch
            ).value
            self.config.save()
            self._set_status("STT settings saved")
        except Exception as e:
            self._set_status(f"Save failed: {e}")

    # ── Logs ──────────────────────────────────────────────────────────────

    @work(exclusive=True, group="logs")
    async def _load_logs(self) -> None:
        log_widget = self.query_one("#log-viewer", RichLog)
        log_widget.clear()
        log_widget.write("[dim]Loading logs...[/]")

        try:
            proc = await asyncio.create_subprocess_exec(
                "journalctl",
                "--user",
                "-u", "claudible.service",
                "--no-pager",
                "-n", "200",
                "--output", "short-iso",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            log_widget.clear()
            if stdout:
                for line in stdout.decode(errors="replace").splitlines():
                    log_widget.write(line)
            elif stderr:
                log_widget.write(f"[red]{stderr.decode(errors='replace')}[/]")
            else:
                log_widget.write("[dim]No logs found. Is the claudible service installed?[/]")
                log_widget.write("[dim]Run: claudible daemon install[/]")
        except FileNotFoundError:
            log_widget.clear()
            log_widget.write("[red]journalctl not found — systemd logging unavailable[/]")
        except Exception as e:
            log_widget.clear()
            log_widget.write(f"[red]Error loading logs: {e}[/]")

    def _clear_logs(self) -> None:
        self.query_one("#log-viewer", RichLog).clear()

    # ── Dashboard info ────────────────────────────────────────────────────

    def _update_dashboard_info(self) -> None:
        updates = {
            "#dash-voice": f"[dim]Voice:[/] [bold]{self.config.tts.voice}[/]",
            "#dash-server-addr": (
                f"[dim]Address:[/] {self.config.tts.host}:{self.config.tts.port}"
            ),
        }

        persona = self.config.rephrase.persona
        rephrase_state = "[green]on[/]" if self.config.rephrase.enabled else "[red]off[/]"
        updates["#dash-persona"] = (
            f"[dim]Persona:[/] [bold]{persona}[/]  [dim]Rephrase:[/] {rephrase_state}"
        )

        # Hook detection
        hooks_settings = Path.home() / ".claude" / "settings.json"
        if hooks_settings.exists():
            try:
                import json

                data = json.loads(hooks_settings.read_text())
                hooks = data.get("hooks", {})
                has_hook = any(
                    "claudible" in str(h)
                    for hook_list in hooks.values()
                    for h in (hook_list if isinstance(hook_list, list) else [])
                )
                if has_hook:
                    updates["#dash-hook-status"] = "[dim]Claude Code hook:[/] [green]installed[/]"
                else:
                    updates["#dash-hook-status"] = (
                        "[dim]Claude Code hook:[/] [yellow]not found in settings[/]"
                    )
            except Exception:
                updates["#dash-hook-status"] = "[dim]Claude Code hook:[/] [yellow]unknown[/]"
        else:
            updates["#dash-hook-status"] = (
                "[dim]Claude Code hook:[/] [yellow]not installed[/]  "
                "[dim](run: claudible hooks install)[/]"
            )

        for widget_id, text in updates.items():
            try:
                self.query_one(widget_id, Static).update(text)
            except Exception:
                pass

    # ── Utility ───────────────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#status-bar", Static).update(f" {msg}")
        except Exception:
            pass
