"""Tkinter settings window for claudible — Voice, Keybind, and General tabs."""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from claudible.config import Config
from claudible.tts.voices import list_voices

log = logging.getLogger(__name__)

# Common key choices for PTT and toggle
KEY_CHOICES = [
    "KEY_SCROLLLOCK",
    "KEY_PAUSE",
    "KEY_F13",
    "KEY_F14",
    "KEY_F15",
    "KEY_RIGHTCTRL",
    "KEY_RIGHTALT",
]


class ConfigWindow:
    """Tkinter configuration window with Voice, Keybind, and General tabs."""

    def __init__(self) -> None:
        self.cfg = Config.load()
        self.root = tk.Tk()
        self.root.title("Claudible Settings")
        self.root.geometry("480x480")
        self.root.resizable(False, False)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_voice_tab(notebook)
        self._build_keybind_tab(notebook)
        self._build_dictation_tab(notebook)
        self._build_general_tab(notebook)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.root.destroy).pack(side="right")

    # --- Voice tab ---

    def _build_voice_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Voice")

        # Voice dropdown
        ttk.Label(frame, text="Voice:").grid(row=0, column=0, sticky="w", pady=4)
        voices = [v.name for v in list_voices()] or ["default"]
        self.voice_var = tk.StringVar(value=self.cfg.tts.voice)
        ttk.Combobox(frame, textvariable=self.voice_var, values=voices, state="readonly").grid(
            row=0, column=1, sticky="ew", pady=4, padx=(8, 0)
        )

        # Speed slider
        ttk.Label(frame, text="Speed:").grid(row=1, column=0, sticky="w", pady=4)
        self.speed_var = tk.DoubleVar(value=self.cfg.tts.speed)
        speed_frame = ttk.Frame(frame)
        speed_frame.grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        ttk.Scale(
            speed_frame, from_=0.5, to=2.0, variable=self.speed_var, orient="horizontal"
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(speed_frame, textvariable=self.speed_var, width=4).pack(side="right")

        # Language
        ttk.Label(frame, text="Language:").grid(row=2, column=0, sticky="w", pady=4)
        self.lang_var = tk.StringVar(value=self.cfg.tts.language)
        ttk.Entry(frame, textvariable=self.lang_var, width=6).grid(
            row=2, column=1, sticky="w", pady=4, padx=(8, 0)
        )

        # Buttons row
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        ttk.Button(btn_row, text="Test Voice", command=self._test_voice).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Add Voice...", command=self._add_voice).pack(side="left", padx=4)

        # Help text
        ttk.Label(
            frame,
            text="Voice samples: 6\u201330s clear speech WAV, no background music.",
            foreground="gray",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        frame.columnconfigure(1, weight=1)

    def _test_voice(self) -> None:
        """Send a test phrase to the TTS server."""
        import asyncio

        from claudible.tts.client import TTSClient

        voice = self.voice_var.get()
        client = TTSClient(base_url=f"http://{self.cfg.tts.host}:{self.cfg.tts.port}")
        try:
            ok = asyncio.run(
                client.speak("Hello, this is a voice test from claudible.", voice=voice)
            )
            if not ok:
                messagebox.showwarning("Test Failed", "TTS server not responding. Is it running?")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _add_voice(self) -> None:
        """Open file dialog, validate, and add a voice sample."""
        path = filedialog.askopenfilename(
            title="Select Voice Sample",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        if not path:
            return

        from claudible.tts.voices import process_voice_sample, validate_voice_sample

        source = Path(path)
        issues = validate_voice_sample(source)

        errors = [i for i in issues if i.startswith("ERROR:")]
        warnings = [i for i in issues if not i.startswith("ERROR:")]

        if errors:
            messagebox.showerror("Invalid Sample", "\n".join(errors))
            return

        if warnings:
            proceed = messagebox.askyesno(
                "Warnings", "\n".join(warnings) + "\n\nContinue anyway?"
            )
            if not proceed:
                return

        # Ask for voice name
        name_dialog = tk.Toplevel(self.root)
        name_dialog.title("Voice Name")
        name_dialog.geometry("300x100")
        name_dialog.transient(self.root)
        name_dialog.grab_set()

        ttk.Label(name_dialog, text="Voice name:").pack(padx=12, pady=(12, 4), anchor="w")
        name_var = tk.StringVar(value=source.stem)
        name_entry = ttk.Entry(name_dialog, textvariable=name_var)
        name_entry.pack(padx=12, fill="x")
        name_entry.focus_set()

        def _do_add() -> None:
            name = name_var.get().strip()
            if not name:
                return
            try:
                voice = process_voice_sample(source, name)
                messagebox.showinfo("Success", f"Voice '{voice.name}' added.")
                # Refresh voice dropdown
                voices = [v.name for v in list_voices()] or ["default"]
                self.voice_var.set(name)
                # Update the combobox values
                for widget in self.root.winfo_children():
                    self._update_voice_combo(widget, voices)
            except ValueError as e:
                messagebox.showerror("Error", str(e))
            name_dialog.destroy()

        ttk.Button(name_dialog, text="Add", command=_do_add).pack(pady=8)

    def _update_voice_combo(self, widget: tk.Widget, voices: list[str]) -> None:
        """Recursively find and update voice combobox values."""
        if isinstance(widget, ttk.Combobox) and widget.cget("textvariable"):
            try:
                if str(widget.cget("textvariable")) == str(self.voice_var):
                    widget.configure(values=voices)
                    return
            except Exception:
                pass
        for child in widget.winfo_children():
            self._update_voice_combo(child, voices)

    # --- Keybind tab ---

    def _build_keybind_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Keybinds")

        # Toggle key (global on/off)
        ttk.Label(frame, text="Toggle Key:").grid(row=0, column=0, sticky="w", pady=4)
        self.toggle_key_var = tk.StringVar(value=self.cfg.stt.toggle_key)
        ttk.Combobox(frame, textvariable=self.toggle_key_var, values=KEY_CHOICES).grid(
            row=0, column=1, sticky="ew", pady=4, padx=(8, 0)
        )
        ttk.Label(frame, text="Global hotkey to toggle STT on/off", foreground="gray").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=(0, 0)
        )

        # PTT key
        ttk.Label(frame, text="PTT Key:").grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.ptt_key_var = tk.StringVar(value=self.cfg.stt.push_to_talk_key)
        ttk.Combobox(frame, textvariable=self.ptt_key_var, values=KEY_CHOICES).grid(
            row=2, column=1, sticky="ew", pady=(12, 4), padx=(8, 0)
        )

        # Hold mode
        self.hold_var = tk.BooleanVar(value=self.cfg.stt.hold_mode)
        ttk.Checkbutton(frame, text="Hold mode (hold key to talk)", variable=self.hold_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=4
        )

        # Vosk model
        ttk.Label(frame, text="Vosk Model:").grid(row=4, column=0, sticky="w", pady=(12, 4))
        vosk_models = self._find_vosk_models()
        self.vosk_model_var = tk.StringVar(value=self.cfg.stt.vosk_model)
        ttk.Combobox(frame, textvariable=self.vosk_model_var, values=vosk_models).grid(
            row=4, column=1, sticky="ew", pady=(12, 4), padx=(8, 0)
        )
        ttk.Label(frame, text="Model directory name in ~/.local/share/vosk/", foreground="gray").grid(
            row=5, column=0, columnspan=2, sticky="w"
        )

        # Input group warning
        import grp
        import os

        username = os.getenv("USER", "")
        try:
            input_grp = grp.getgrnam("input")
            in_group = username in input_grp.gr_mem or os.getgid() == input_grp.gr_gid
        except KeyError:
            in_group = False

        if not in_group:
            ttk.Label(
                frame,
                text=f"Warning: '{username}' not in 'input' group.\n"
                "PTT/toggle keys require input group access.",
                foreground="red",
            ).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)

        frame.columnconfigure(1, weight=1)

    @staticmethod
    def _find_vosk_models() -> list[str]:
        """List installed vosk model directories."""
        vosk_dir = Path.home() / ".local" / "share" / "vosk"
        if not vosk_dir.exists():
            return ["small"]
        models = [d.name for d in sorted(vosk_dir.iterdir()) if d.is_dir()]
        return models or ["small"]

    # --- Dictation tab ---

    def _build_dictation_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Dictation")

        ttk.Label(
            frame,
            text="Voice keywords that trigger key presses instead of typing text.",
            foreground="gray",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # Headers
        ttk.Label(frame, text="Keyword (spoken)", font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Label(frame, text="Key press", font=("", 9, "bold")).grid(
            row=1, column=1, sticky="w", padx=(0, 8)
        )

        # Editable keyword rows
        self._kw_rows: list[tuple[tk.StringVar, tk.StringVar, ttk.Frame]] = []
        self._kw_container = ttk.Frame(frame)
        self._kw_container.grid(row=2, column=0, columnspan=3, sticky="nsew")

        common_keys = [
            "Return", "BackSpace", "Tab", "Escape", "space",
            "Up", "Down", "Left", "Right",
            "Delete", "Home", "End", "Page_Up", "Page_Down",
            "F1", "F2", "F3", "F4", "F5",
        ]

        for i, (word, key) in enumerate(self.cfg.dictation.keywords.items()):
            self._add_kw_row(i, word, key, common_keys)

        # Add / remove buttons
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btn_row, text="+ Add Keyword", command=lambda: self._add_kw_row(
            len(self._kw_rows), "", "Return", common_keys
        )).pack(side="left", padx=4)

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(2, weight=1)

    def _add_kw_row(
        self, idx: int, word: str, key: str, common_keys: list[str] | None = None,
    ) -> None:
        if common_keys is None:
            common_keys = ["Return", "BackSpace", "Tab", "Escape", "space"]

        row_frame = ttk.Frame(self._kw_container)
        row_frame.pack(fill="x", pady=2)

        word_var = tk.StringVar(value=word)
        key_var = tk.StringVar(value=key)

        ttk.Entry(row_frame, textvariable=word_var, width=16).pack(side="left", padx=(0, 8))
        ttk.Combobox(row_frame, textvariable=key_var, values=common_keys, width=14).pack(
            side="left", padx=(0, 8)
        )

        def _remove(rf: ttk.Frame = row_frame, entry: tuple = None) -> None:
            # Find and remove from list
            self._kw_rows[:] = [(w, k, f) for w, k, f in self._kw_rows if f is not rf]
            rf.destroy()

        ttk.Button(row_frame, text="x", width=2, command=_remove).pack(side="left")

        self._kw_rows.append((word_var, key_var, row_frame))

    # --- General tab ---

    def _build_general_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="General")

        # TTS server host
        ttk.Label(frame, text="TTS Host:").grid(row=0, column=0, sticky="w", pady=4)
        self.host_var = tk.StringVar(value=self.cfg.tts.host)
        ttk.Entry(frame, textvariable=self.host_var, width=20).grid(
            row=0, column=1, sticky="w", pady=4, padx=(8, 0)
        )

        # TTS server port
        ttk.Label(frame, text="TTS Port:").grid(row=1, column=0, sticky="w", pady=4)
        self.port_var = tk.IntVar(value=self.cfg.tts.port)
        ttk.Entry(frame, textvariable=self.port_var, width=8).grid(
            row=1, column=1, sticky="w", pady=4, padx=(8, 0)
        )

        # Separator
        ttk.Separator(frame, orient="horizontal").grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=12
        )

        # Rephrase enabled
        self.rephrase_var = tk.BooleanVar(value=self.cfg.rephrase.enabled)
        ttk.Checkbutton(
            frame, text="Enable rephrase (Ollama)", variable=self.rephrase_var
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        # Ollama model
        ttk.Label(frame, text="Ollama Model:").grid(row=4, column=0, sticky="w", pady=4)
        self.ollama_model_var = tk.StringVar(value=self.cfg.rephrase.model)
        ttk.Entry(frame, textvariable=self.ollama_model_var, width=20).grid(
            row=4, column=1, sticky="w", pady=4, padx=(8, 0)
        )

        # Persona
        ttk.Label(frame, text="Persona:").grid(row=5, column=0, sticky="w", pady=4)
        self.persona_var = tk.StringVar(value=self.cfg.rephrase.persona)
        ttk.Entry(frame, textvariable=self.persona_var, width=20).grid(
            row=5, column=1, sticky="w", pady=4, padx=(8, 0)
        )

        frame.columnconfigure(1, weight=1)

    # --- Save ---

    def _save(self) -> None:
        # Voice tab
        self.cfg.tts.voice = self.voice_var.get()
        self.cfg.tts.speed = round(self.speed_var.get(), 2)
        self.cfg.tts.language = self.lang_var.get()

        # Keybind tab
        self.cfg.stt.toggle_key = self.toggle_key_var.get()
        self.cfg.stt.push_to_talk_key = self.ptt_key_var.get()
        self.cfg.stt.hold_mode = self.hold_var.get()
        self.cfg.stt.vosk_model = self.vosk_model_var.get()

        # Dictation tab — collect keyword rows
        keywords: dict[str, str] = {}
        for word_var, key_var, _ in self._kw_rows:
            word = word_var.get().strip().lower()
            key = key_var.get().strip()
            if word and key:
                keywords[word] = key
        self.cfg.dictation.keywords = keywords

        # General tab
        self.cfg.tts.host = self.host_var.get()
        self.cfg.tts.port = self.port_var.get()
        self.cfg.rephrase.enabled = self.rephrase_var.get()
        self.cfg.rephrase.model = self.ollama_model_var.get()
        self.cfg.rephrase.persona = self.persona_var.get()

        self.cfg.save()

        # Write nerd-dictation config file from keywords
        self._write_nerd_dictation_config(keywords)

        log.info("Config saved")
        self.root.destroy()

    @staticmethod
    def _write_nerd_dictation_config(keywords: dict[str, str]) -> None:
        """Write ~/.config/nerd-dictation/nerd-dictation.py from keyword map."""
        config_dir = Path.home() / ".config" / "nerd-dictation"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "nerd-dictation.py"

        # Build the keywords dict literal
        items = "\n".join(f'    "{word}": "{key}",' for word, key in keywords.items())

        config_file.write_text(
            '"""nerd-dictation config — generated by claudible settings."""\n'
            "\n"
            "import subprocess\n"
            "\n"
            "KEYWORD_KEYS = {\n"
            f"{items}\n"
            "}\n"
            "\n"
            "\n"
            "def nerd_dictation_process(text: str) -> str:\n"
            '    words = text.strip().split()\n'
            '    out = []\n'
            '    for word in words:\n'
            '        key = KEYWORD_KEYS.get(word.lower())\n'
            '        if key:\n'
            '            subprocess.run(["xdotool", "key", "--clearmodifiers", key], check=False)\n'
            '        else:\n'
            '            out.append(word)\n'
            '    return " ".join(out)\n',
            encoding="utf-8",
        )

    def run(self) -> None:
        self.root.mainloop()
