"""Textual TUI for claudible configuration and control."""

from __future__ import annotations

import asyncio

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListView,
    ListItem,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from claudible.config import Config
from claudible.rephrase.personas import PERSONAS, list_personas
from claudible.tts.client import TTSClient
from claudible.tts.voices import list_voices


class ClaudibleApp(App):
    """Claudible configuration and control TUI."""

    TITLE = "Claudible"
    CSS = """
    Screen {
        layout: vertical;
    }
    #status-label {
        color: $text-muted;
        text-style: italic;
        margin: 0 1;
        height: 1;
    }
    .section-title {
        text-style: bold;
        margin: 1 0 0 0;
    }
    .field-row {
        layout: horizontal;
        height: 3;
        margin: 0 0;
    }
    .field-label {
        width: 20;
        content-align: right middle;
        padding: 0 1;
    }
    .field-input {
        width: 1fr;
    }
    .btn-row {
        layout: horizontal;
        height: 3;
        margin: 1 0;
    }
    .btn-row Button {
        margin: 0 1;
    }
    #server-indicator {
        margin: 1 0;
    }
    #rephrase-output {
        height: 6;
        border: solid $primary;
        margin: 1 0;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = Config.load()
        self.client = TTSClient(
            base_url=f"http://{self.config.tts.host}:{self.config.tts.port}"
        )

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("", id="status-label")
        with TabbedContent():
            with TabPane("Server", id="tab-server"):
                yield from self._compose_server_tab()
            with TabPane("Voices", id="tab-voices"):
                yield from self._compose_voices_tab()
            with TabPane("Config", id="tab-config"):
                yield from self._compose_config_tab()
            with TabPane("STT/PTT", id="tab-stt"):
                yield from self._compose_stt_tab()
            with TabPane("Rephrase", id="tab-rephrase"):
                yield from self._compose_rephrase_tab()
        yield Footer()

    # --- Tab composers ---

    def _compose_server_tab(self):
        yield Static("TTS Server", classes="section-title")
        yield Static("Status: checking...", id="server-indicator")
        with Horizontal(classes="field-row"):
            yield Label("Host:Port", classes="field-label")
            yield Static(
                f"{self.config.tts.host}:{self.config.tts.port}", id="server-hostport"
            )
        with Horizontal(classes="btn-row"):
            yield Button("Start Server", id="btn-server-start", variant="success")
            yield Button("Stop Server", id="btn-server-stop", variant="error")
            yield Button("Refresh", id="btn-server-refresh")

    def _compose_voices_tab(self):
        yield Static("Installed Voices", classes="section-title")
        yield ListView(id="voices-list")
        with Horizontal(classes="btn-row"):
            yield Button("Test Selected", id="btn-voice-test")
            yield Button("Refresh", id="btn-voices-refresh")

    def _compose_config_tab(self):
        yield Static("TTS Settings", classes="section-title")
        with Horizontal(classes="field-row"):
            yield Label("Host", classes="field-label")
            yield Input(value=self.config.tts.host, id="cfg-tts-host", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Port", classes="field-label")
            yield Input(value=str(self.config.tts.port), id="cfg-tts-port", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Model", classes="field-label")
            yield Input(value=self.config.tts.model, id="cfg-tts-model", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Voice", classes="field-label")
            yield Input(value=self.config.tts.voice, id="cfg-tts-voice", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Language", classes="field-label")
            yield Input(value=self.config.tts.language, id="cfg-tts-lang", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Speed", classes="field-label")
            yield Input(value=str(self.config.tts.speed), id="cfg-tts-speed", classes="field-input")

        yield Static("Rephrase Settings", classes="section-title")
        with Horizontal(classes="field-row"):
            yield Label("Enabled", classes="field-label")
            yield Switch(value=self.config.rephrase.enabled, id="cfg-rephrase-enabled")
        with Horizontal(classes="field-row"):
            yield Label("Ollama URL", classes="field-label")
            yield Input(
                value=self.config.rephrase.ollama_url,
                id="cfg-rephrase-url",
                classes="field-input",
            )
        with Horizontal(classes="field-row"):
            yield Label("Model", classes="field-label")
            yield Input(
                value=self.config.rephrase.model,
                id="cfg-rephrase-model",
                classes="field-input",
            )

        with Horizontal(classes="btn-row"):
            yield Button("Save Config", id="btn-config-save", variant="primary")

    def _compose_stt_tab(self):
        yield Static("Speech-to-Text / Push-to-Talk", classes="section-title")
        ptt_keys = [
            ("KEY_SCROLLLOCK", "KEY_SCROLLLOCK"),
            ("KEY_PAUSE", "KEY_PAUSE"),
            ("KEY_F13", "KEY_F13"),
            ("KEY_F24", "KEY_F24"),
        ]
        with Horizontal(classes="field-row"):
            yield Label("PTT Key", classes="field-label")
            yield Select(
                options=ptt_keys,
                value=self.config.stt.push_to_talk_key,
                id="cfg-stt-key",
            )
        with Horizontal(classes="field-row"):
            yield Label("Hold Mode", classes="field-label")
            yield Switch(value=self.config.stt.hold_mode, id="cfg-stt-hold")
        with Horizontal(classes="field-row"):
            yield Label("VOSK Model", classes="field-label")
            yield Input(
                value=self.config.stt.vosk_model,
                id="cfg-stt-vosk",
                classes="field-input",
            )
        with Horizontal(classes="btn-row"):
            yield Button("Save STT Config", id="btn-stt-save", variant="primary")

    def _compose_rephrase_tab(self):
        yield Static("Rephrase Preview", classes="section-title")
        persona_options = [(p, p) for p in list_personas()]
        with Horizontal(classes="field-row"):
            yield Label("Persona", classes="field-label")
            yield Select(
                options=persona_options,
                value=self.config.rephrase.persona,
                id="rephrase-persona",
            )
        yield Static("", id="rephrase-prompt-preview")
        with Horizontal(classes="field-row"):
            yield Label("Test Input", classes="field-label")
            yield Input(
                placeholder="Type text to rephrase...",
                id="rephrase-test-input",
                classes="field-input",
            )
        with Horizontal(classes="btn-row"):
            yield Button("Test Rephrase", id="btn-rephrase-test", variant="primary")
        yield Static("(output will appear here)", id="rephrase-output")

    # --- Lifecycle ---

    def on_mount(self) -> None:
        self._refresh_server_status()
        self._refresh_voices()
        self._update_persona_preview()
        self.set_interval(5.0, self._refresh_server_status)

    # --- Event handlers ---

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "btn-server-start":
            await self._start_server()
        elif btn == "btn-server-stop":
            await self._stop_server()
        elif btn == "btn-server-refresh":
            self._refresh_server_status()
        elif btn == "btn-voice-test":
            await self._test_voice()
        elif btn == "btn-voices-refresh":
            self._refresh_voices()
        elif btn == "btn-config-save":
            self._save_config()
        elif btn == "btn-stt-save":
            self._save_stt_config()
        elif btn == "btn-rephrase-test":
            self._do_rephrase_test()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "rephrase-persona":
            self._update_persona_preview()

    # --- Async workers ---

    @work(exclusive=True)
    async def _refresh_server_status(self) -> None:
        indicator = self.query_one("#server-indicator", Static)
        try:
            healthy = await self.client.health()
            if healthy:
                indicator.update("[green]Status: RUNNING[/green]")
            else:
                indicator.update("[red]Status: NOT RUNNING[/red]")
        except Exception:
            indicator.update("[red]Status: NOT RUNNING[/red]")

    async def _start_server(self) -> None:
        self._set_status("Starting server in background...")
        import subprocess
        import sys

        subprocess.Popen(
            [sys.executable, "-m", "claudible.cli", "server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        await asyncio.sleep(2)
        self._refresh_server_status()
        self._set_status("Server start requested")

    async def _stop_server(self) -> None:
        self._set_status("Stopping server...")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{self.client.base_url}/shutdown")
            self._set_status("Server stopped")
        except Exception:
            self._set_status("Failed to stop server (may not be running)")
        await asyncio.sleep(1)
        self._refresh_server_status()

    async def _test_voice(self) -> None:
        lv = self.query_one("#voices-list", ListView)
        if lv.highlighted_child is None:
            self._set_status("No voice selected")
            return
        voice_name = str(lv.highlighted_child.children[0].renderable)
        self._set_status(f"Testing voice: {voice_name}")
        ok = await self.client.speak("Hello, this is a voice test from claudible.", voice=voice_name)
        if ok:
            self._set_status(f"Voice test sent: {voice_name}")
        else:
            self._set_status("Voice test failed — is the server running?")

    def _refresh_voices(self) -> None:
        lv = self.query_one("#voices-list", ListView)
        lv.clear()
        for v in list_voices():
            lv.append(ListItem(Label(v.name)))

    def _save_config(self) -> None:
        try:
            self.config.tts.host = self.query_one("#cfg-tts-host", Input).value
            self.config.tts.port = int(self.query_one("#cfg-tts-port", Input).value)
            self.config.tts.model = self.query_one("#cfg-tts-model", Input).value
            self.config.tts.voice = self.query_one("#cfg-tts-voice", Input).value
            self.config.tts.language = self.query_one("#cfg-tts-lang", Input).value
            self.config.tts.speed = float(self.query_one("#cfg-tts-speed", Input).value)
            self.config.rephrase.enabled = self.query_one("#cfg-rephrase-enabled", Switch).value
            self.config.rephrase.ollama_url = self.query_one("#cfg-rephrase-url", Input).value
            self.config.rephrase.model = self.query_one("#cfg-rephrase-model", Input).value
            self.config.save()
            self._set_status("Config saved!")
        except (ValueError, Exception) as e:
            self._set_status(f"Save failed: {e}")

    def _save_stt_config(self) -> None:
        try:
            key_select = self.query_one("#cfg-stt-key", Select)
            if key_select.value is not Select.BLANK:
                self.config.stt.push_to_talk_key = str(key_select.value)
            self.config.stt.hold_mode = self.query_one("#cfg-stt-hold", Switch).value
            self.config.stt.vosk_model = self.query_one("#cfg-stt-vosk", Input).value
            self.config.save()
            self._set_status("STT config saved!")
        except (ValueError, Exception) as e:
            self._set_status(f"Save failed: {e}")

    @work(exclusive=True)
    async def _do_rephrase_test(self) -> None:
        text = self.query_one("#rephrase-test-input", Input).value.strip()
        if not text:
            self._set_status("Enter text to rephrase")
            return

        output = self.query_one("#rephrase-output", Static)
        output.update("Rephrasing...")
        self._set_status("Sending to Ollama...")

        persona_select = self.query_one("#rephrase-persona", Select)
        persona = str(persona_select.value) if persona_select.value is not Select.BLANK else "default"

        # Temporarily set persona for rephrase call
        original_persona = self.config.rephrase.persona
        original_enabled = self.config.rephrase.enabled
        self.config.rephrase.persona = persona
        self.config.rephrase.enabled = True

        try:
            from claudible.rephrase.ollama import rephrase
            result = await rephrase(text, config=self.config)
            output.update(result)
            self._set_status("Rephrase complete")
        except Exception as e:
            output.update(f"Error: {e}")
            self._set_status("Rephrase failed")
        finally:
            self.config.rephrase.persona = original_persona
            self.config.rephrase.enabled = original_enabled

    def _update_persona_preview(self) -> None:
        select = self.query_one("#rephrase-persona", Select)
        persona = str(select.value) if select.value is not Select.BLANK else "default"
        prompt = PERSONAS.get(persona, PERSONAS["default"])
        preview = self.query_one("#rephrase-prompt-preview", Static)
        preview.update(f"[dim]{prompt}[/dim]")

    def _set_status(self, msg: str) -> None:
        self.query_one("#status-label", Label).update(msg)
