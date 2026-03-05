# Claudible Test Plan

## Current State

- **1 test file** (`tests/test_filter.py`) with 10 tests covering `extract_speakable()`
- **41 Python modules**, ~1% test coverage
- **Known failing test**: `test_command_output_skipped` — filter doesn't skip lines after `$` prompts
- **Test deps**: pytest >= 8.0, pytest-asyncio >= 0.24, ruff >= 0.6
- **No conftest.py** or shared fixtures

---

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_config.py                 # Config load/save/migrate
├── test_lifecycle.py              # PID file management
├── test_filter.py                 # EXISTING (extend in-place)
├── test_filter_options.py         # extract_options + IVR formatting
├── test_stop_hook.py              # Stop hook _extract_text, main() modes
├── test_installer.py              # Hook install/uninstall/is_installed
├── test_personas.py               # Persona loading, listing, custom
├── test_ollama.py                 # Rephrase + completion (mocked HTTP)
├── test_tts_client.py             # TTSClient (mocked HTTP)
├── test_tts_voices.py             # Voice discovery, validation, combine
├── test_stt_dictation.py          # Dictation subprocess (mocked)
├── test_stt_windows.py            # Window state I/O, register, validate
├── test_stt_procwatch.py          # Process watcher (mocked /proc)
├── test_stt_callback.py           # Callback script generation
├── test_web_router.py             # FastAPI endpoint tests (TestClient)
├── test_cli.py                    # Click CLI via CliRunner
└── fixtures/
    └── sample.wav                 # Minimal valid WAV for voice tests
```

---

## conftest.py — Shared Fixtures

```python
# Fixtures needed across multiple test files:

tmp_config(tmp_path)        # Write a default config.toml, set CONFIG_FILE
tmp_voices_dir(tmp_path)    # Empty voices dir, monkeypatch VOICES_DIR
tmp_window_state(tmp_path)  # Temp windows.json path, monkeypatch WINDOW_STATE
tmp_pid_file(tmp_path)      # Temp PID file path, monkeypatch PID_FILE
sample_wav(tmp_path)        # Generate a 7s silence WAV at 22050 Hz mono
mock_xdotool(monkeypatch)   # Patch subprocess.check_output for xdotool calls
```

---

## Module Tests

### 1. `test_config.py` — Config load/save/migrate

| # | Test | Description |
|---|------|-------------|
| 1 | `test_load_defaults` | `Config.load()` on missing file returns all defaults |
| 2 | `test_load_from_file` | Write a TOML with custom values, verify they load |
| 3 | `test_save_roundtrip` | `Config.load()` → mutate → `save()` → `load()` matches |
| 4 | `test_migrate_ollama_url` | `rephrase.ollama_url` → `rephrase.api_url` + `/v1` suffix |
| 5 | `test_migrate_bogus_model` | `rephrase.model = "Select.blah"` is stripped |
| 6 | `test_migrate_idempotent` | Running `_migrate` twice doesn't double-transform |
| 7 | `test_stt_defaults` | New fields: `watched_processes`, `process_watch_interval` have correct defaults |
| 8 | `test_unknown_keys_ignored` | Extra TOML keys don't crash pydantic (model_validate) |

### 2. `test_lifecycle.py` — PID management

| # | Test | Description |
|---|------|-------------|
| 1 | `test_write_read_pid` | `write_pid()` → `read_pid()` returns current PID |
| 2 | `test_read_pid_missing` | No PID file → returns None |
| 3 | `test_read_pid_corrupt` | PID file with "garbage" → returns None |
| 4 | `test_is_running_self` | Write own PID → `is_running()` returns True |
| 5 | `test_is_running_stale` | Write dead PID (99999999) → `is_running()` returns False, cleans up |
| 6 | `test_remove_pid` | `remove_pid()` deletes file; safe if already missing |
| 7 | `test_stop_running_no_process` | `stop_running()` with no PID file returns False |

### 3. `test_filter.py` — extract_speakable (extend existing)

Keep existing 10 tests. Add:

| # | Test | Description |
|---|------|-------------|
| 11 | `test_empty_string` | `""` → None |
| 12 | `test_whitespace_only` | `"   \n  "` → None |
| 13 | `test_nested_code_blocks` | Two consecutive code blocks with prose between |
| 14 | `test_horizontal_rule_skipped` | `"---"` line is noise |
| 15 | `test_git_hash_line_skipped` | `"a1b2c3d some commit msg"` is noise |
| 16 | `test_cli_command_noise` | `"pip install foo"` is noise |
| 17 | `test_key_value_noise` | `"host=localhost"` is noise |
| 18 | `test_inline_code_stripped` | `` "Use `foo` to bar" `` → "Use to bar" (code removed) |
| 19 | `test_long_technical_ratio_skipped` | Mostly paths/hashes → None |
| 20 | `test_truncation_preserves_question` | Short text ending in `?` is kept even if < 15 chars |
| 21 | `test_shell_prompt_with_blank_line` | `$ cmd\noutput\n\nprose` → prose only |
| 22 | `test_markdown_header_noise` | `"### Output"` is skipped |
| 23 | `test_bullet_file_path_noise` | `"- /usr/bin/foo"` is noise |
| 24 | `test_clean_line_removes_flags` | `"Run it --verbose to see"` → `"Run it to see"` |
| 25 | `test_is_technical_token_versions` | `"1.2.3"` is technical |
| 26 | `test_is_technical_token_camelcase` | `"someMethod"` is technical |

### 4. `test_filter_options.py` — extract_options + IVR

| # | Test | Description |
|---|------|-------------|
| 1 | `test_extract_two_options` | `"1. Foo\n2. Bar"` → `[(1,"Foo"), (2,"Bar")]` |
| 2 | `test_extract_parens_style` | `"1) Foo\n2) Bar"` → same result |
| 3 | `test_single_option_returns_none` | Only 1 numbered item → None |
| 4 | `test_options_in_code_block_ignored` | Options inside ``` fences → None |
| 5 | `test_markdown_bold_stripped` | `"1. **Bold option**"` → `(1, "Bold option")` |
| 6 | `test_inline_code_stripped` | `` "1. Use `foo`" `` → `(1, "Use foo")` |
| 7 | `test_empty_text` | `""` → None |
| 8 | `test_none_text` | `None` → None |
| 9 | `test_format_ivr_basic` | `_format_ivr("Choose:", [(1,"A"),(2,"B")])` returns IVR string |
| 10 | `test_format_ivr_empty_preamble` | `_format_ivr("", options)` → options only |
| 11 | `test_format_ivr_strips_raw_numbers` | Raw `"1. A 2. B"` text cleaned before appending IVR |

### 5. `test_stop_hook.py` — Hook entry point

| # | Test | Description |
|---|------|-------------|
| 1 | `test_extract_text_normal` | `{"last_assistant_message": "hello"}` → `"hello"` |
| 2 | `test_extract_text_nested` | `{"message": {"content": "hi"}}` → `"hi"` |
| 3 | `test_extract_text_empty` | `{}` → None |
| 4 | `test_extract_text_whitespace` | `{"last_assistant_message": "  "}` → None |
| 5 | `test_main_off_mode` | Mode "off" → no TTS call (mock stdin + config) |
| 6 | `test_main_completion_mode` | Mode "completion" → calls `_announce_completion`, not `_process` |
| 7 | `test_main_questions_mode_no_question` | Mode "questions", no `?` → completion announced |
| 8 | `test_main_questions_mode_with_question` | Mode "questions", has `?` → speaks it |
| 9 | `test_main_full_mode` | Mode "full" → filters + speaks |
| 10 | `test_main_mute_flag` | TTS_MUTE_FLAG exists → returns immediately |
| 11 | `test_main_truncation` | Input > 2000 chars → truncated with "... truncated." |
| 12 | `test_main_invalid_json` | Non-JSON stdin → silent failure |

### 6. `test_installer.py` — Hook install/uninstall

| # | Test | Description |
|---|------|-------------|
| 1 | `test_install_creates_file` | `install_hook()` creates settings.json with hook entry |
| 2 | `test_install_idempotent` | Second `install_hook()` doesn't duplicate |
| 3 | `test_is_installed_true` | After install → `is_installed()` returns True |
| 4 | `test_is_installed_false` | No settings.json → False |
| 5 | `test_uninstall_removes_entry` | `uninstall_hook()` removes only claudible entry |
| 6 | `test_uninstall_preserves_others` | Other hooks in Stop list are kept |
| 7 | `test_uninstall_missing_file` | No settings.json → returns True (no-op) |

### 7. `test_personas.py` — Persona management

| # | Test | Description |
|---|------|-------------|
| 1 | `test_list_builtin_personas` | All 12 built-in names present |
| 2 | `test_get_builtin_prompt` | `get_persona_prompt("jarvis")` returns JARVIS prompt |
| 3 | `test_get_unknown_returns_default` | `get_persona_prompt("nonexistent")` → default prompt |
| 4 | `test_custom_persona_loaded` | Write `.txt` file → appears in `list_personas()` |
| 5 | `test_custom_overrides_builtin` | Custom "jarvis.txt" overrides built-in |
| 6 | `test_is_custom` | Custom → True, built-in → False |
| 7 | `test_empty_custom_file_skipped` | Empty `.txt` file not loaded |

### 8. `test_ollama.py` — Rephrase API (mocked)

| # | Test | Description |
|---|------|-------------|
| 1 | `test_rephrase_disabled` | `enabled=False` → returns original text, no HTTP call |
| 2 | `test_rephrase_success` | Mock 200 with choices → returns rephrased text |
| 3 | `test_rephrase_api_error` | Mock 500 → returns original text (graceful fallback) |
| 4 | `test_rephrase_timeout` | Mock timeout → returns original text |
| 5 | `test_rephrase_empty_response` | Mock 200 with empty choices → returns original |
| 6 | `test_rephrase_with_api_key` | Verify Authorization header sent when api_key set |
| 7 | `test_generate_quip_success` | Mock 200 → returns quip string |
| 8 | `test_generate_quip_failure` | Mock error → returns None |
| 9 | `test_list_models_success` | Mock 200 with models → returns list |
| 10 | `test_list_models_failure` | Mock error → returns [] |

Use `pytest-httpx` or `respx` or `unittest.mock.patch` on `httpx.AsyncClient`.

### 9. `test_tts_client.py` — TTS HTTP client (mocked)

| # | Test | Description |
|---|------|-------------|
| 1 | `test_speak_success` | Mock 200 → returns True |
| 2 | `test_speak_failure` | Mock 500 → returns False |
| 3 | `test_speak_with_options` | Verify voice/language/speed in payload |
| 4 | `test_speak_defaults` | Only text sent when defaults used |
| 5 | `test_health_ok` | Mock 200 → True |
| 6 | `test_health_down` | ConnectError → False |
| 7 | `test_speak_sync_success` | Mock 200 → returns True |
| 8 | `test_speak_sync_connection_error` | ConnectError → False |

### 10. `test_tts_voices.py` — Voice management

| # | Test | Description |
|---|------|-------------|
| 1 | `test_list_voices_empty` | Empty dir → [] |
| 2 | `test_list_voices_finds_dirs` | Create dirs with .wav → found |
| 3 | `test_list_voices_skips_no_wav` | Dir without .wav → skipped |
| 4 | `test_get_voice_found` | Existing voice → Voice object |
| 5 | `test_get_voice_missing` | Missing → FileNotFoundError |
| 6 | `test_voice_wav_file` | `voice.wav_file` returns .wav path |
| 7 | `test_voice_wav_file_missing` | No .wav → FileNotFoundError |
| 8 | `test_add_voice` | Copies file into voice dir |
| 9 | `test_validate_too_short` | < 6s WAV → ERROR |
| 10 | `test_validate_good_sample` | 7s 22050 Hz mono → no issues |
| 11 | `test_validate_wrong_rate` | 44100 Hz → warning (not error) |
| 12 | `test_validate_stereo` | 2 channels → warning |
| 13 | `test_validate_long` | > 30s → warning |
| 14 | `test_process_voice_sample` | Resamples + installs as sample.wav |
| 15 | `test_process_voice_fatal_error` | Too short → ValueError |
| 16 | `test_combine_samples` | Multiple clips → combined WAV at 22050 Hz |
| 17 | `test_combine_no_sources` | Empty list → ValueError |
| 18 | `test_get_voice_info` | Returns dict with duration, sample_rate, etc. |

Requires `soundfile` + `numpy`. Use the `sample_wav` fixture from conftest.

### 11. `test_stt_dictation.py` — Dictation wrapper (mocked subprocess)

| # | Test | Description |
|---|------|-------------|
| 1 | `test_is_available_found` | `shutil.which` returns path → True |
| 2 | `test_is_available_missing` | `shutil.which` returns None → False |
| 3 | `test_is_running_false_initially` | Not started → False |
| 4 | `test_start_spawns_subprocess` | Mock Popen, verify cmd includes model dir |
| 5 | `test_start_already_running` | Second start() is a no-op |
| 6 | `test_start_not_available` | Raises RuntimeError |
| 7 | `test_stop_calls_end` | Verify `nerd-dictation end` called |
| 8 | `test_model_path_resolution` | Verify candidate paths checked in order |
| 9 | `test_noise_suppression_flag` | `noise_suppression=True` adds `--pulse-device-name` |

### 12. `test_stt_windows.py` — Window state I/O

| # | Test | Description |
|---|------|-------------|
| 1 | `test_read_empty_state` | Missing file → `{"windows": {}, "default_slot": "1"}` |
| 2 | `test_write_read_roundtrip` | Write state → read back matches |
| 3 | `test_register_window_manual` | Mock xdotool → state has window_id + title |
| 4 | `test_register_with_explicit_id` | Pass window_id directly → stored |
| 5 | `test_unregister_window` | Remove slot → gone from state |
| 6 | `test_unregister_missing_slot` | No-op, no error |
| 7 | `test_clear_all_windows` | Deletes state file |
| 8 | `test_validate_window_alive` | Mock xdotool success → True |
| 9 | `test_validate_window_dead` | Mock xdotool failure → False |
| 10 | `test_capture_active_window` | Mock xdotool getactivewindow → (wid, title) |
| 11 | `test_capture_active_window_wayland` | Mock xdotool failure → RuntimeError |

### 13. `test_stt_procwatch.py` — Process watcher

| # | Test | Description |
|---|------|-------------|
| 1 | `test_scan_proc_finds_match` | Create fake /proc entries → found |
| 2 | `test_scan_proc_filters_uid` | Other user's process → not returned |
| 3 | `test_scan_proc_no_match` | No matching names → [] |
| 4 | `test_find_terminal_window` | Mock /proc/PID/stat + xdotool → returns window ID |
| 5 | `test_find_terminal_window_wayland` | All xdotool calls fail → None |
| 6 | `test_get_window_title` | Mock xdotool getwindowname → title string |
| 7 | `test_watcher_assigns_slot` | Poll with live process → slot 1 assigned |
| 8 | `test_watcher_prunes_dead_pid` | PID dies → slot freed |
| 9 | `test_watcher_lowest_free_slot` | Slot 1 occupied → new proc gets slot 2 |
| 10 | `test_watcher_same_window_reuse` | New PID in same terminal → updates existing slot |
| 11 | `test_watcher_manual_not_pruned` | Entry without `pid` field → never removed |
| 12 | `test_watcher_start_stop` | Thread starts and stops cleanly |
| 13 | `test_pid_alive_check` | Live PID → True; dead PID → False |

For most of these, monkeypatch `os.listdir("/proc")`, `/proc/<pid>/comm`, etc. to avoid real proc scanning.

### 14. `test_stt_callback.py` — Callback script generation

| # | Test | Description |
|---|------|-------------|
| 1 | `test_generate_callback` | Generates valid Python script at expected path |
| 2 | `test_callback_has_keywords` | Generated script contains keyword dict from config |
| 3 | `test_callback_has_trigger_words` | Trigger words embedded correctly |
| 4 | `test_callback_wakeword_disabled` | `WAKEWORD_ENABLED = False` when disabled |
| 5 | `test_callback_window_lock_path` | Window state path embedded |
| 6 | `test_remove_callback` | `remove_callback()` deletes the file |
| 7 | `test_generated_script_parseable` | `compile(script, ...)` doesn't raise SyntaxError |

### 15. `test_web_router.py` — FastAPI endpoint tests

Use `httpx.AsyncClient` with `app` from `fastapi.testclient` or `httpx` ASGITransport.

| # | Test | Description |
|---|------|-------------|
| 1 | `test_get_config` | GET /api/config → 200 with all sections |
| 2 | `test_patch_config_tts` | PATCH /api/config/tts `{"speed": 1.5}` → 200 |
| 3 | `test_patch_config_unknown_section` | PATCH /api/config/bogus → 400 |
| 4 | `test_get_voices` | GET /api/voices → list |
| 5 | `test_get_personas` | GET /api/personas → list with names |
| 6 | `test_put_persona` | PUT /api/personas/test-p → creates custom persona |
| 7 | `test_delete_persona` | DELETE /api/personas/test-p → removes it |
| 8 | `test_get_windows` | GET /api/windows → list with pid/process fields |
| 9 | `test_get_windows_watched` | GET /api/windows/watched → watched_processes list |
| 10 | `test_post_windows_register` | POST /api/windows/register → registers slot |
| 11 | `test_delete_window_slot` | DELETE /api/windows/1 → removes slot |
| 12 | `test_delete_windows_all` | DELETE /api/windows → clears all |
| 13 | `test_get_status` | GET /api/status → model_loaded, hook_installed, etc. |
| 14 | `test_rephrase_test` | POST /api/rephrase/test → result (mock ollama) |
| 15 | `test_get_logs` | GET /api/logs → logs string |
| 16 | `test_stt_restart` | POST /api/stt/restart → ok (with mock callback) |
| 17 | `test_hook_test_options` | POST /api/hook/test-options → options detected |

Needs significant mocking of engine, voices, xdotool, etc.

### 16. `test_cli.py` — Click CLI commands

Use `click.testing.CliRunner`.

| # | Test | Description |
|---|------|-------------|
| 1 | `test_main_no_command` | `claudible` → status output with version |
| 2 | `test_version` | `claudible --version` → version string |
| 3 | `test_voices_list_empty` | No voices → "No voices installed" |
| 4 | `test_voices_list_populated` | Create voice dirs → listed |
| 5 | `test_personas_list` | Lists built-in + custom |
| 6 | `test_personas_show` | `personas show jarvis` → prompt text |
| 7 | `test_windows_list_empty` | No windows → "No windows registered" |
| 8 | `test_windows_list_with_process` | Entry with pid/process → shows process info |
| 9 | `test_windows_list_manual` | Entry without pid → shows "(manual)" |
| 10 | `test_hooks_status_installed` | Mock is_installed=True → "is installed" |
| 11 | `test_hooks_status_not_installed` | Mock is_installed=False → "NOT installed" |
| 12 | `test_speak_server_down` | Mock client failure → error exit code |

---

## Mocking Strategy

### What to mock (never hit real services/hardware)

| Dependency | Mock approach |
|---|---|
| `/proc` filesystem | Monkeypatch `os.listdir`, `open()` for proc entries, or use `tmp_path` |
| `xdotool` | Monkeypatch `subprocess.check_output` / `subprocess.run` |
| `nerd-dictation` | Monkeypatch `shutil.which`, `subprocess.Popen` |
| TTS server (httpx) | `respx` or `unittest.mock.patch("httpx.AsyncClient")` |
| Ollama API (httpx) | Same as above |
| `soundfile` / `sounddevice` | Real for voice tests (generate synthetic WAV), mock for audio playback |
| evdev (keyboards) | Don't test directly — keybind.py is integration-level |
| pystray (tray icon) | Don't test directly — GUI is integration-level |
| Config file paths | Monkeypatch `CONFIG_FILE`, `VOICES_DIR`, etc. to `tmp_path` |
| PID file | Monkeypatch `PID_FILE` to `tmp_path` |
| Settings.json | Monkeypatch `SETTINGS_FILE` to `tmp_path` |
| Persona dir | Monkeypatch `_PERSONA_DIR` to `tmp_path` |

### What NOT to test (hardware/integration)

- `gui/tray.py` — requires X11 display + pystray + GTK
- `gui/icons.py` — requires Pillow (tested indirectly via tray)
- `tts/engine.py` — requires GPU + XTTS model (~2GB)
- `tts/audio.py` — requires audio device
- `stt/keybind.py` internals — requires `/dev/input/` devices
- `stt/noise.py` — requires PipeWire
- `setup/wizard.py` — interactive, requires system deps
- `tui/app.py` — requires Textual + terminal

---

## Priority Order

Implementation order based on risk/value:

1. **conftest.py** — fixtures everything else needs
2. **test_config.py** — foundation; config bugs break everything
3. **test_filter.py extensions** — core speech filtering, known bug
4. **test_filter_options.py** — IVR options, user-facing
5. **test_stop_hook.py** — hook is the main integration point with Claude
6. **test_installer.py** — hook install correctness is critical
7. **test_stt_procwatch.py** — new code, needs validation
8. **test_stt_windows.py** — window state correctness
9. **test_lifecycle.py** — singleton enforcement
10. **test_personas.py** — straightforward, low mock overhead
11. **test_tts_voices.py** — requires soundfile but well-isolated
12. **test_tts_client.py** — HTTP client, mock httpx
13. **test_ollama.py** — HTTP client, mock httpx
14. **test_stt_dictation.py** — subprocess wrapper
15. **test_stt_callback.py** — template generation
16. **test_web_router.py** — most complex, many mocks needed
17. **test_cli.py** — end-to-end CLI, many mocks needed

---

## Running Tests

```bash
# All tests
pytest tests/

# Single file
pytest tests/test_config.py -v

# With coverage
pytest tests/ --cov=claudible --cov-report=term-missing

# Fast: skip slow voice processing tests
pytest tests/ -m "not slow"
```

Mark voice processing tests with `@pytest.mark.slow` (they read/write WAV files).

---

## CI Considerations

- Tests should run without GPU, audio devices, X11, or network
- All external calls (httpx, subprocess, /proc) must be mocked
- WAV fixtures should be generated synthetically (numpy), not committed as binaries
- Target: all tests pass in < 30 seconds
