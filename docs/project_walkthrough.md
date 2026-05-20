# Anki Voice Field Project Walkthrough

This walkthrough explains what was built, how the pieces fit together, why the
design changed over time, and what to study if you want to understand the
project as a programmer.

I inspected the current repository and the available git history. Where I infer
motivation from commit names, file diffs, or code shape, I label it as inference.

## 1. Project Synopsis

`anki_voice_field` is a Windows-focused Python MVP that lets you record a voice
note while reviewing Anki cards, transcribe that audio locally, and append the
transcript into the current card's note.

The main user-facing purpose is fast note capture during Anki review:

1. Start reviewing a card in Anki.
2. Press `F8` or use the Anki menu action.
3. Speak.
4. Press `F8` again.
5. The app transcribes your speech.
6. The app appends the transcript to the correct note field with a timestamp.
7. A transcript popup or review popup lets you confirm what happened.

The project has two phases:

| Phase | What It Is | Why It Exists |
| --- | --- | --- |
| Phase 1 | External Python helper app | Handles microphone recording, transcription, AnkiConnect calls, queueing, and verification outside Anki. |
| Phase 2 | Native Anki add-on controller | Adds an Anki-local hotkey/menu and starts/controls the helper without making you run PowerShell manually every time. |

The important technical components are:

| Component | Role |
| --- | --- |
| AnkiConnect | Local HTTP API used by the helper to read/update Anki notes. |
| `sounddevice` | Captures microphone audio. |
| `faster-whisper` | Local speech-to-text engine. |
| Tkinter | Status window, review popup, transcript popup. |
| Local control server | Lets the Anki add-on send commands to the helper through `127.0.0.1`. |
| Anki add-on | Registers Anki menu actions and the `F8` shortcut inside Anki. |

The output is appended HTML in a target note field:

```html
<hr>
<b>Voice Note - YYYY-MM-DD HH:MM</b><br>
transcribed text here
```

The target field selection order is:

1. `Lecture Notes`
2. `Remarks`, when the note type looks like Image Occlusion
3. `Back`
4. `Extra`
5. `Back Extra`
6. `Remarks`

If none of those fields exists, the helper stops and reports the available
fields instead of guessing.

## 2. Repository Structure

Important tracked files and folders:

| Path | Responsibility |
| --- | --- |
| `README.md` | Main user-facing setup, usage, and packaging notes. |
| `PHASES.md` | Explains Phase 1 external helper and Phase 2 Anki controller. |
| `BEGINNER_NOTES.py` | Teaching notes written as Python triple-quoted explanations. |
| `requirements.txt` | Python dependencies for recording, hotkeys, numerical audio arrays, and local Whisper transcription. |
| `config.py` | Central runtime settings for the helper: field names, ports, hotkey, model size, retries, timeouts, logs, and audio settings. |
| `anki_client.py` | All AnkiConnect API calls, field selection, append formatting, HTML escaping, and write verification helpers. |
| `recorder.py` | Microphone recording and WAV file writing. |
| `transcriber.py` | Lazy loading and reuse of the `faster-whisper` model. |
| `main.py` | Command-line workflow for dry run, real run, and `--test-anki`. |
| `launcher.pyw` | Main GUI/status-window helper with queueing, review mode, fast mode, local control server, popups, and background work. |
| `control_server.py` | Small local HTTP server used by the Anki add-on to tell the helper to record/stop/show/test. |
| `session_log.py` | Writes successful voice notes to `voice_notes_log.txt` as a local backup. |
| `single_instance.py` | Prevents running multiple helper instances by binding to a localhost port. |
| `run_dry.ps1` | Convenience PowerShell wrapper for `python main.py --dry-run`. |
| `run_wet.ps1` | Convenience PowerShell wrapper for `python main.py`. |
| `start_anki_voice_field.vbs` | Starts `launcher.pyw` minimized through `pythonw.exe`, hiding the terminal. |
| `open_status_window.vbs` | Starts `launcher.pyw` with the status window visible. |
| `setup_helper_env.ps1` | Creates `.venv` and installs requirements in whichever folder the script lives in. |
| `install_personal_addon.ps1` | Copies the add-on into Anki's `addons21` folder and copies helper files into its bundled `helper/` folder. |
| `package_addon.ps1` | Builds `dist/anki_voice_field.ankiaddon`. |
| `dist/anki_voice_field.ankiaddon` | Shareable Anki add-on package. It includes source files, not the full dependency environment or model cache. |
| `tests/test_append_format.py` | Unit tests for append formatting, field fallback, verification helper, and session log output. |
| `anki_addon/anki_voice_field/` | Native Anki add-on package. It controls the external helper. |

Important generated or ignored files:

| Path | Why It Matters |
| --- | --- |
| `.venv/` | Local Python virtual environment. Not committed. |
| `anki_voice_field.log` | Runtime log from the helper. Ignored because it is local state. |
| `voice_notes_log.txt` | Plaintext backup of successful transcripts. Ignored because it contains personal study notes. |
| `voice_note_temp*.wav` | Temporary audio recordings. Ignored. |
| `build/` | Temporary package build folder. Ignored. |

## 3. What We Changed / Built

The git history is short and useful. Some commits appear non-linear because the
GitHub initial README was merged after the main local work had already started.

| Commit | Summary | What It Represents |
| --- | --- | --- |
| `6827d77` | `Checkpoint phase 1 and add personal Anki controller` | The first large working version: external helper, AnkiConnect client, recorder, transcriber, Tkinter launcher, native controller, tests, docs, scripts. |
| `c8e320b` | `Limit card-change wait to risky fields` | An attempt to make saving faster by only waiting for Anki to move off certain fields before writing. |
| `59e65d4` | `Simplify Anki add-on menu` | Reduced menu complexity so the main visible Anki action is Record / Stop. |
| `c9a93ef` | `Improve Anki recording status messages` | Clarified status text so starting and stopping recording felt less confusing. |
| `6a791c6` | `Restore safe append wait for all fields` | Reverted toward safer write behavior after append reliability issues. |
| `fb613d4` | `Make fast mode auto-save after card change` | Made fast mode wait quietly until the target card changes, then save automatically without a review click. |
| `a069956` | `Document add-on packaging for sharing` | Added more package/share documentation. |
| `7faaa6a` | `Bundle helper source in add-on package` | Changed packaging so the `.ankiaddon` includes the helper source and setup script. |
| `921695b` | `Avoid surprise helper setup on Anki startup` | Prevented Anki from unexpectedly launching setup/downloads; preserves installed `.venv` during personal reinstalls. |

Main features built:

| Feature | Current Behavior |
| --- | --- |
| Push-to-talk recording | `F8` toggles start/stop. |
| Local transcription | `faster-whisper` transcribes WAV audio locally. |
| Dry run | `python main.py --dry-run` records/transcribes and previews the field update without writing. |
| Anki connection test | `python main.py --test-anki` checks AnkiConnect and prints current card/note details. |
| Safe append | Existing field HTML is preserved; new note is appended below it. |
| Field fallback | Falls back from `Lecture Notes` to Image Occlusion `Remarks`, then common back/extra fields. |
| Review mode | Shows editable transcript before saving. |
| Fast mode | Auto-saves after transcription, with a read-only transcript confirmation. |
| Queueing | A stopped recording becomes a job so you can record the next card while transcription continues. |
| Write verification | After updating Anki, the helper reads the note back and verifies the transcript stayed there. |
| Backup log | Successful saves are also written to `voice_notes_log.txt`. |
| Native Anki controller | Anki owns the hotkey/menu and sends commands to the helper over localhost. |
| Add-on packaging | `package_addon.ps1` creates `dist/anki_voice_field.ankiaddon`. |

## 4. Why These Changes Were Made

### External Helper First

The project began as an external Python script because microphone access,
hotkeys, and Whisper dependencies are easier to manage in a normal Python
environment than inside Anki's bundled Python runtime.

Tradeoff: the helper needs its own `.venv`, dependencies, and process lifecycle.
The Anki add-on is therefore a controller, not the full engine.

### AnkiConnect Instead Of Native Writes At First

The helper talks to Anki through AnkiConnect at `http://localhost:8765`. This
made the first MVP simple:

```python
invoke("updateNoteFields", {"note": {"id": note_id, "fields": {field_name: value}}})
```

Tradeoff: AnkiConnect writes can conflict with Anki's reviewer/editor state.
That is why later reliability code waits for card changes and verifies writes.

### Start Recording Immediately

In `launcher.pyw`, recording starts before the helper finishes locking the Anki
card. The target card is locked in a background thread.

Reason: speed. If the app waits on AnkiConnect before opening the microphone,
pressing `F8` feels slow.

Tradeoff: if AnkiConnect fails while you are already recording, the recording is
discarded when you stop. This is better than recording the wrong note.

### Queueing

Stopped recordings are placed into `job_queue`. The helper processes one voice
job at a time in `_job_worker`.

Reason: local Whisper transcription can be slow. Queueing lets you continue
reviewing and recording instead of waiting for each transcription to finish.

Tradeoff: background jobs make state management harder. Each job must remember
the original `card_id`, `note_id`, `field_name`, and mode flags.

### Review Mode And Fast Mode

Review mode exists because transcription can be wrong. It shows an editable
popup before writing.

Fast mode exists because Anki review speed matters. It writes automatically and
only shows a read-only confirmation after saving.

Tradeoff: review mode is safer but interrupts flow; fast mode is faster but can
save a bad transcript.

### Wait For Card Change Before Saving

The helper waits until Anki is no longer showing the target review card before
writing certain fields. In fast mode, this wait can be indefinite because
`FAST_MODE_WAIT_FOR_CARD_CHANGE_SECONDS = None`.

Reason: the project hit a real reliability issue where AnkiConnect appeared to
accept an update, but Anki later overwrote the field when the review card state
finished saving.

Tradeoff: this improves reliability but means you often need to answer/move off
the card before the append is actually written.

### Read-Back Verification And Retries

After `updateNoteFields`, the helper reads the note back and checks for the
timestamp and transcript lines. It retries up to `SAVE_RETRY_ATTEMPTS`.

Reason: AnkiConnect can return success while the visible/persistent note field
does not end up changed.

Tradeoff: verification adds delay, but it prevents false "success" messages.

### Native Anki Add-on As Controller

The add-on registers a menu item and `F8`, then sends `/toggle` to the helper's
local control server.

Reason: this keeps the user inside Anki. Anki owns the hotkey, and the helper
does the heavy work outside Anki.

Tradeoff: there are two processes and a localhost API instead of one pure Anki
add-on.

### No Surprise Setup On Startup

The latest change added:

- `auto_launch_helper_on_anki_startup: true`
- `auto_setup_helper: false`
- preservation of the add-on helper `.venv` during personal reinstalls

Reason: startup should be quiet once the helper is installed. A setup/download
window should not appear every time Anki starts.

Tradeoff: on a fresh computer, the user must still run one-time setup manually
or enable auto setup.

## 5. Code Walkthrough

### Configuration: `config.py`

`config.py` centralizes most runtime settings:

| Setting Group | Examples | Why It Exists |
| --- | --- | --- |
| Target fields | `TARGET_FIELD_NAME`, fallback fields | Keeps field behavior configurable. |
| Hotkeys and ports | `HOTKEY`, `CONTROL_SERVER_PORT`, `INSTANCE_LOCK_PORT` | Coordinates keyboard and localhost communication. |
| Runtime files | `AUDIO_TEMP_FILE`, `LOG_FILE`, `VOICE_NOTES_LOG_FILE` | Keeps generated files near the helper. |
| Save safety | retry counts, verify timeouts, card-change waits | Controls reliability behavior. |
| Audio | sample rate and channels | Defines microphone capture format. |
| Whisper | model size, device, compute type | Controls local transcription speed/quality. |
| Medical transcription | medical mode, prompt, glossary, language, beam size | Biases speech-to-text toward medical terminology. |

What could break if changed incorrectly:

- Changing ports can break add-on/helper communication.
- Changing field names can make notes go to the wrong field or fail fallback.
- Lowering verification waits too much can cause false failures.
- Disabling card-change waits can reintroduce Anki overwriting appended text.

### Anki API Layer: `anki_client.py`

This module is the helper's boundary with AnkiConnect.

Key pieces:

| Function/Class | What It Does |
| --- | --- |
| `invoke()` | Sends JSON requests to AnkiConnect and returns the result. |
| `check_connection()` | Calls AnkiConnect `version`. |
| `get_current_card_note()` | Reads current reviewer card, card info, note info, fields, deck, and model. |
| `get_current_review_card()` | Faster current-card read using `guiCurrentCard`, useful when starting recording. |
| `resolve_note_id_from_card()` | Converts card ID to note ID. |
| `choose_target_field()` | Applies the field priority rules. |
| `append_transcript_to_field()` | Appends the formatted voice note block without overwriting existing field contents. |
| `field_contains_appended_transcript()` | Checks whether a saved field contains the expected timestamp and transcript. |
| `update_note_field()` | Calls AnkiConnect `updateNoteFields`. |

Data flow:

1. The helper asks AnkiConnect for the current card.
2. It extracts field values and model name.
3. It chooses a target field.
4. Later, it re-reads the note fields by note ID.
5. It builds a new field value by appending HTML.
6. It sends only that one field update back to Anki.

Important safety detail: `append_transcript_to_field()` returns:

```python
if not existing_field_html:
    return block
return f"{existing_field_html}\n{block}"
```

That small function is central to the "append, do not overwrite" promise.

What could break if changed incorrectly:

- If `invoke()` is changed, every Anki operation can fail.
- If `choose_target_field()` is changed carelessly, voice notes can land in the
  wrong field.
- If HTML escaping is removed, transcript text containing `<` or `>` could
  become unintended HTML.
- If `update_note_field()` sends more fields than intended, the project could
  violate the "do not bulk edit" safety rule.

### Recording: `recorder.py`

`Recorder` wraps `sounddevice.InputStream`.

Execution flow:

1. `start()` creates an input stream and begins collecting microphone chunks.
2. `_capture_chunk()` receives audio arrays from the sounddevice callback.
3. `stop()` closes the stream, concatenates chunks, and writes a WAV file.
4. `_write_wav()` converts float audio in `[-1.0, 1.0]` into 16-bit PCM.

Why it exists: it isolates audio capture so the rest of the app can just ask for
a finished WAV file.

What could break if changed incorrectly:

- Wrong sample rate/channels can hurt transcription quality.
- Not copying callback audio could lead to corrupted chunks.
- Reusing the same temp path could make queued jobs overwrite each other. The
  current code uses unique temp files.

### Transcription: `transcriber.py`

This module lazy-loads a single global Whisper model:

```python
_MODEL: Any | None = None
_MODEL_LOCK = threading.Lock()
```

`get_model()` imports `WhisperModel`, creates it once, and reuses it. The lock
prevents two threads from creating separate models at the same time.

The transcription call also builds options from `config.py`:

| Option | Purpose |
| --- | --- |
| `WHISPER_LANGUAGE` | Pins transcription to English by default. |
| `WHISPER_BEAM_SIZE` | Controls decoding search width. Current default favors speed. |
| `MEDICAL_TRANSCRIPTION_PROMPT` | Gives Whisper medical context before it transcribes. |
| `MEDICAL_GLOSSARY` | Supplies common terms as hotwords. |

This is not a medical correctness guarantee. It is a biasing mechanism: it gives
the model more context so similar-sounding terms are more likely to be decoded
as medical language.

Why it exists: loading a Whisper model is expensive. Reusing one model makes
later notes faster.

What could break if changed incorrectly:

- Removing the lock can create race conditions during preload/transcription.
- Changing model size, beam size, or medical glossary affects speed and
  accuracy.
- Removing the empty transcript check could append blank voice notes.

### Command-Line Flow: `main.py`

`main.py` is the original MVP workflow.

Main paths:

| Command | Behavior |
| --- | --- |
| `python main.py --test-anki` | Checks AnkiConnect and prints current card/note info. |
| `python main.py --dry-run` | Records and transcribes, then previews the update without saving. |
| `python main.py` | Records, transcribes, appends, writes, verifies, and logs. |

Step-by-step for a real run:

1. `main()` parses flags.
2. `run()` acquires the single-instance lock.
3. It checks AnkiConnect.
4. It reads and locks the current note/card.
5. It chooses the target field.
6. `record_once_with_hotkey()` waits for `F8`, records, then waits for `F8` again.
7. `transcribe_audio()` returns text.
8. The note is re-read by note ID.
9. The field is appended.
10. If not dry-run, browser/editor selection is checked.
11. The helper may wait for the target card to stop being current.
12. It writes through AnkiConnect.
13. It reads back repeatedly until the append is verified.
14. It writes a plaintext backup entry to `voice_notes_log.txt`.

What could break if changed incorrectly:

- Recording before locking the note would risk saving to the wrong card.
- Writing without re-reading current note fields could overwrite newer field
  changes.
- Removing read-back verification could make failures look like successes.

### GUI Helper And Queue: `launcher.pyw`

`launcher.pyw` is the daily-use helper. It is larger than `main.py` because it
manages UI, background work, queueing, review popups, and add-on control.

Important objects:

| Object | Role |
| --- | --- |
| `VoiceJob` | Immutable data packet for one recording job. |
| `VoiceFieldApp` | Main Tkinter application and workflow coordinator. |
| `events` queue | Thread-safe messages from worker threads to the Tkinter UI thread. |
| `job_queue` | Background queue of recordings waiting for transcription/save. |
| `anki_write_lock` | Prevents two queued jobs from writing to Anki at the same time. |

Startup flow:

1. `main()` acquires the single-instance lock.
2. It creates `tk.Tk()`.
3. `VoiceFieldApp` builds the UI.
4. It optionally starts the global hotkey listener.
5. It starts the local control server.
6. It starts the job worker thread.
7. It starts model preload in the background if configured.

Recording flow:

1. A global hotkey, Anki command, or button sends a toggle event.
2. `toggle_recording()` debounces repeated key events.
3. `start_recording_for_current_card()` starts the microphone immediately.
4. `_lock_current_card_worker()` reads the current Anki card in the background.
5. On stop, `Recorder.stop()` returns a unique WAV path.
6. A `VoiceJob` is put into `job_queue`.
7. The UI becomes ready for the next recording while the job is processed.

Processing flow:

1. `_job_worker()` takes one job from the queue.
2. `_process_voice_job()` resolves note ID if needed.
3. It transcribes the audio.
4. Review mode sends a `review_transcript` event and stops.
5. Fast mode builds the append and calls `_write_and_verify()`.
6. Success writes to `voice_notes_log.txt` and shows a transcript popup.

Review popup flow:

1. `show_review_popup()` opens an editable transcript window.
2. `Save To Anki` starts `_append_reviewed_transcript_worker()`.
3. `Re-record` records again for the same locked note.
4. `Cancel` writes nothing.

Save safety flow:

`_write_and_verify()` is the heart of write reliability:

1. Lock `anki_write_lock`.
2. Refuse to write if the note is selected in Anki Browser.
3. Wait for card change when configured.
4. Call `update_note_field()`.
5. Poll `get_note_fields()`.
6. Confirm the timestamp and transcript are present.
7. Sleep briefly and verify again so the update is stable.
8. Retry if needed.

What could break if changed incorrectly:

- Tkinter UI changes must happen on the main thread. Worker threads should send
  events instead of directly touching widgets.
- Queue jobs must keep their original card/note identity. Otherwise a late
  transcription could save to the card currently on screen instead of the card
  you spoke about.
- Removing `anki_write_lock` could let two saves interleave.
- Changing fast-mode wait behavior can make the app faster but less reliable.

### Local Control Server: `control_server.py`

The helper exposes a tiny localhost API:

| Route | Used For |
| --- | --- |
| `/health` | Add-on checks whether helper is alive. |
| `/toggle` | Start or stop recording. |
| `/show` | Show the helper window. |
| `/test-anki` | Ask helper to run its Anki test. |

This server runs only on `127.0.0.1`, so it is local to the machine.

Why it exists: Anki and the helper are separate processes. The add-on needs a
simple way to command the helper.

What could break if changed incorrectly:

- Changing paths breaks the add-on.
- Changing the port must be updated in both `config.py` and add-on config.
- Long-running work should not happen inside the request handler; it should
  schedule work back into the Tkinter app, as `/toggle` currently does.

### Native Anki Add-on: `anki_addon/anki_voice_field/__init__.py`

This file runs inside Anki.

Its jobs are:

1. Load add-on config with defaults.
2. Resolve the bundled helper folder.
3. Register `Tools > Anki Voice Field: Record / Stop`.
4. Register the Anki-local `F8` shortcut.
5. Quietly start the helper on Anki startup if the helper `.venv` already exists.
6. Send `/toggle`, `/show`, or `/test-anki` requests to the helper.

Important config defaults:

```json
{
  "helper_project_folder": "__BUNDLED__",
  "helper_pythonw_path": "__AUTO__",
  "auto_launch_helper_on_anki_startup": true,
  "auto_setup_helper": false
}
```

`__BUNDLED__` means:

```text
Anki add-on folder / helper
```

`__AUTO__` means:

```text
helper/.venv/Scripts/pythonw.exe
```

This matters: the installed add-on's helper `.venv` is separate from the project
root `.venv` unless you change config.

What could break if changed incorrectly:

- If the add-on starts the helper with the global hotkey enabled, both Anki and
  the helper may respond to `F8`.
- If `auto_setup_helper` is turned on, Anki may launch PowerShell setup on first
  use. That may be acceptable on a fresh machine, but it should not happen
  every startup.
- If `helper_project_folder` points to the wrong place, the add-on will not find
  `launcher.pyw`.

### Packaging Scripts

`install_personal_addon.ps1` copies add-on files into:

```text
%APPDATA%\Anki2\addons21\anki_voice_field
```

It also copies helper files into:

```text
%APPDATA%\Anki2\addons21\anki_voice_field\helper
```

Recent behavior: it preserves an existing `helper/.venv` before replacing the
add-on folder. This prevents repeated dependency setup during development.

`package_addon.ps1` builds:

```text
dist/anki_voice_field.ankiaddon
```

It copies the add-on source, copies helper source files into `helper/`, removes
`__pycache__`, zips the result, and renames it to `.ankiaddon`.

Important packaging limitation: the package includes helper source and setup
script, not the full `.venv`, compiled dependencies, or Whisper model cache.
That is why a fresh laptop still needs one-time setup.

## 6. Important Concepts I Should Learn

### Virtual Environments

A `.venv` is a local Python environment. It keeps this project's packages
separate from system Python and from other projects.

In this project there can be more than one relevant `.venv`:

| Environment | Used By |
| --- | --- |
| Project root `.venv` | CLI, VBS launchers, development commands. |
| Installed add-on `helper/.venv` | The bundled helper launched by Anki. |

That distinction matters for laptop setup.

### HTTP APIs And JSON

AnkiConnect is a local HTTP API. The helper sends JSON like:

```json
{
  "action": "version",
  "version": 6,
  "params": {}
}
```

The control server is also an HTTP API, but it is built by this project and used
only locally by the Anki add-on.

### Event-Driven Programming

Hotkeys, button clicks, HTTP requests, and background workers do not run in one
straight line. They produce events.

`launcher.pyw` uses an `events` queue so worker threads can ask the UI thread to
update labels, logs, and popups safely.

### Threads

Threads allow several things to happen at once:

- Tkinter UI stays responsive.
- Microphone recording can happen while Anki card locking runs.
- Transcription jobs run in the background.
- The control server responds to Anki.
- Whisper model preloads while the app is already open.

The cost is complexity. Shared state needs care, and UI work must stay on the
Tkinter main thread.

### Queues

A queue is a first-in, first-out line of work. Here, each stopped recording
becomes a `VoiceJob`.

This is a major design idea: when you speak about card A, the job remembers card
A even if you are already looking at card B by the time transcription finishes.

### Defensive Programming

The project includes many checks because it is editing study data:

- Stop if AnkiConnect is unreachable.
- Stop if no current review card exists.
- Stop if no usable target field exists.
- Do not overwrite the whole note.
- Re-read fields before appending.
- Refuse writes when the note is selected in Anki Browser.
- Verify the append after writing.
- Retry failed/stale writes.
- Save a plaintext backup log only after verified success.

### HTML Escaping

Anki fields are HTML. If a transcript contains `<` or `>`, the code escapes it
so it displays as text instead of becoming markup.

### Idempotence And Verification

The write path is not fully idempotent because retrying with a precomputed
`updated_value` could be affected if the note changes externally between
attempts. But the helper does verify that the expected transcript exists before
reporting success.

This is a good place to study the difference between "API returned success" and
"the system state is actually correct."

### Packaging

An Anki add-on package is a zip file with a `.ankiaddon` extension. This project
builds that package from `anki_addon/anki_voice_field/` and copies helper source
into a bundled `helper/` directory.

The package is source-level, not a complete offline app bundle.

## 7. Error/Debugging History

These areas look like they were added because of real bugs or edge cases.

| Area | Likely Problem Addressed | Evidence |
| --- | --- | --- |
| Card-change wait | Anki overwrote or failed to persist updates while the same review card was active. | Config names, commit history, README discussion, `_wait_until_target_card_is_not_current()`. |
| Read-back verification | AnkiConnect could accept a write but the field did not stay changed. | `field_contains_appended_transcript()`, retry loop, stable delay. |
| Browser selection check | Notes open/selected in Browser/editor may silently reject or overwrite updates. | `get_selected_browser_note_ids()` and explicit error. |
| Queueing | Transcription took too long during fast review. | `VoiceJob`, `job_queue`, "you can record the next card now" logs. |
| Start microphone before card lock completes | Pressing record felt slow. | `self.recorder.start()` happens before `_lock_current_card_worker()`. |
| Debounce hotkey | One physical press could fire multiple events. | `last_hotkey_time` checks in `main.py` and `launcher.pyw`. |
| Single-instance lock | Multiple helpers could fight over hotkeys, ports, or state. | `single_instance.py` binds port `47865`. |
| Add-on menu simplification | Too many menu items were confusing. | `show_advanced_menu_items` config and commit `59e65d4`. |
| No surprise setup | Anki startup or first command unexpectedly opened PowerShell/downloads. | `auto_setup_helper: false` and commit `921695b`. |
| Preserve installed `.venv` | Reinstalling the personal add-on during development forced setup again. | `install_personal_addon.ps1` temporarily moves `helper/.venv`. |

## 8. How To Run The Project

### Prerequisites

Required software:

- Windows
- Python 3.12 or similar modern Python 3
- Anki Desktop
- AnkiConnect add-on installed in Anki
- A working microphone

Python dependencies from `requirements.txt`:

```text
faster-whisper
numpy
pynput
sounddevice
```

No environment variables are required.

### Setup For Project-Root Development

From the project root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Equivalent helper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_helper_env.ps1
```

This creates a `.venv` in the same folder as the script.

### Test AnkiConnect

Open Anki, start reviewing a card, then run:

```powershell
.\.venv\Scripts\python.exe main.py --test-anki
```

Expected result: it prints the AnkiConnect version, current card ID, note ID,
deck, note type, and field names.

### Dry Run

```powershell
.\.venv\Scripts\python.exe main.py --dry-run
```

Expected result: it records/transcribes but does not modify Anki.

### Real CLI Run

```powershell
.\.venv\Scripts\python.exe main.py
```

Press `F8` once to start recording and again to stop.

### GUI Helper

Visible status window:

```powershell
.\.venv\Scripts\pythonw.exe launcher.pyw
```

Start minimized:

```powershell
.\.venv\Scripts\pythonw.exe launcher.pyw --start-minimized
```

The VBS shortcuts do the same thing without a visible terminal:

```text
start_anki_voice_field.vbs
open_status_window.vbs
```

### Personal Anki Add-on Install

For local development, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_personal_addon.ps1
```

Restart Anki after installing.

Important: with default add-on config, `helper_project_folder` is `__BUNDLED__`.
That means Anki looks for the helper at:

```text
%APPDATA%\Anki2\addons21\anki_voice_field\helper
```

On a fresh computer, run setup from that installed helper folder:

```powershell
cd "$env:APPDATA\Anki2\addons21\anki_voice_field\helper"
powershell -ExecutionPolicy Bypass -File .\setup_helper_env.ps1
```

Then restart Anki. Future Anki sessions should not reinstall packages unless
that helper `.venv` is deleted or dependencies change.

### Package The Add-on

```powershell
powershell -ExecutionPolicy Bypass -File .\package_addon.ps1
```

Output:

```text
dist/anki_voice_field.ankiaddon
```

### Install The Packaged Add-on On Another Computer

1. Install Anki Desktop.
2. Install AnkiConnect in Anki.
3. Install `dist/anki_voice_field.ankiaddon` using Anki's add-on install flow.
4. Run the bundled helper setup once from:

```text
%APPDATA%\Anki2\addons21\anki_voice_field\helper\setup_helper_env.ps1
```

5. Restart Anki.
6. Start reviewing and press `F8`.

## 9. How To Verify It Works

### Automated Tests

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Current tests cover:

- appending to an empty field
- preserving an existing field
- escaping transcript HTML
- verifying appended transcript text
- writing the backup log
- target field fallback rules
- medical transcription option building

### Basic Syntax Check

There is no dedicated linter or type checker configured. A basic syntax check
can be run with:

```powershell
.\.venv\Scripts\python.exe -B -c "import ast, pathlib; files=[p for p in pathlib.Path('.').rglob('*.py') if '.venv' not in p.parts and '__pycache__' not in p.parts and 'build' not in p.parts]; [ast.parse(p.read_text(encoding='utf-8')) for p in files]; print('syntax ok for', len(files), 'python files')"
```

### Manual Success Criteria

Before writing to Anki:

- `--test-anki` reports a current card.
- The target field selection matches your expectation.
- `--dry-run` shows the append preview and does not change the card.

For a real append:

- Pressing `F8` starts recording quickly.
- Pressing `F8` again stops recording and queues processing.
- The transcript appears in a popup or review window.
- The correct note gets updated, not the card you moved to later.
- Existing field content remains above the new voice note.
- The appended block contains the expected timestamp and transcript.
- `voice_notes_log.txt` receives a matching backup entry after verified save.

For the Anki add-on:

- Anki starts without a PowerShell setup window once helper `.venv` exists.
- `Tools > Anki Voice Field: Record / Stop` toggles recording.
- `F8` works inside Anki without clicking outside Anki.
- The helper window can still show logs/status if opened.

### Minimum Useful Tests To Add

The current tests are useful but narrow. Good next tests would be:

| Test Type | What To Verify |
| --- | --- |
| Mocked AnkiConnect tests | `invoke()`, `get_current_card_note()`, and `update_note_field()` behavior without requiring real Anki. |
| Queue tests | A `VoiceJob` keeps its original note/card identity. |
| Write verification tests | `_wait_for_verified_append()` succeeds/fails under controlled fake note states. |
| Add-on config tests | `__BUNDLED__` and `__AUTO__` resolve correctly. |
| Packaging test | `.ankiaddon` contains `__init__.py`, `config.json`, `manifest.json`, and required helper files. |

## 10. Issues or Risks Noted

These are observations only. I did not change application logic.

| Risk | Why It Matters | Severity |
| --- | --- | --- |
| Add-on helper setup path can be confusing | Project root `.venv` and installed bundled helper `.venv` are different. Running setup in the wrong folder may not help the add-on. | High for new installs |
| `anki_addon/README.md` appears stale | It says the add-on opens PowerShell setup on first use, but current default config has `auto_setup_helper: false`. | Medium |
| Dependency versions are unpinned | Future `faster-whisper`, `sounddevice`, or `pynput` releases could break installs. | Medium |
| Medical glossary is generic | It will help common medical terms, but your own weak spots need to be added manually in `config.py`. | Low |
| Native add-on duplicates append/field logic | `anki_addon/__init__.py` has its own `choose_target_field()` and append helpers, which can drift from `anki_client.py`. | Medium |
| Anki write timing is inherently fragile | The helper still has to wait for card changes to avoid Anki overwrites. This is reliable but can feel slow or confusing. | Medium |
| Fast mode can wait indefinitely | `FAST_MODE_WAIT_FOR_CARD_CHANGE_SECONDS = None`, so fast mode waits until the user moves off the card. | Medium |
| Local control server has no authentication | It binds to `127.0.0.1`, which is low risk, but any local process could hit `/toggle`. | Low to Medium |
| Transcripts are saved in plaintext logs | `voice_notes_log.txt` is useful but may contain private study notes. | Medium privacy |
| `.ankiaddon` is not an offline dependency bundle | A fresh laptop still needs one-time helper setup and possibly a Whisper model download. | Expected limitation |
| No full integration test with Anki | Current tests do not prove real AnkiConnect writes work. | Medium |
| Build/install scripts are Windows-specific | This is expected for now but limits portability. | Low |
| Existing logs/audio can remain locally | Ignored files can contain personal data if not cleaned. | Low to Medium privacy |

## 11. Suggested Next Improvements

### Critical

Code quality / reliability:

- Add a clear first-time setup command or menu item for the installed bundled
  helper. The current behavior avoids surprise setup, which is good, but a fresh
  laptop needs a very obvious setup path.
- Pin dependency versions in `requirements.txt` after confirming a known-good
  set on your machine.
- Add a packaging verification test so every `.ankiaddon` includes the expected
  helper files.

Feature / product:

- Decide whether the add-on should keep using AnkiConnect writes or move final
  note writes into native Anki code. Native writes may reduce the "move off the
  card before saving" problem, but they would require careful testing.

### Useful

Code quality:

- Remove duplication between `anki_client.py` and the Anki add-on's native debug
  append helpers.
- Split `launcher.pyw` into smaller modules once behavior stabilizes:
  UI, job processing, Anki write service, and review popup handling.
- Add mocked tests for AnkiConnect responses and write verification.
- Add a small diagnostic command that prints which helper folder and `.venv` the
  add-on is using.

Feature:

- Add a simple settings UI or config explanation for:
  - target fields
  - review mode default
  - transcript popup duration
  - model size
  - medical glossary terms
- Add a visible "setup helper" action that only appears when `.venv` is missing.
- Add a privacy toggle for the plaintext backup log.

### Nice-To-Have

Code quality:

- Add `ruff` or another formatter/linter.
- Add type checking with `mypy` or `pyright` after the code is split into
  smaller modules.
- Add a release checklist for packaging and laptop testing.

Feature:

- Show a small non-intrusive Anki tooltip with the final saved transcript.
- Add optional model choices like `tiny`, `base`, or `small`.
- Add a transcript history viewer.
- Add optional cleanup for old temp WAV files and old logs.

## Highest-Value Study Path

If you want to learn this project deeply, study in this order:

1. `tests/test_append_format.py`
2. `append_transcript_to_field()` in `anki_client.py`
3. `choose_target_field()` in `anki_client.py`
4. `invoke()` and `get_current_card_note()` in `anki_client.py`
5. `Recorder.start()` and `Recorder.stop()` in `recorder.py`
6. `transcribe_audio()` and `get_model()` in `transcriber.py`
7. `main.run()` in `main.py`
8. `VoiceJob` and `_process_voice_job()` in `launcher.pyw`
9. `_write_and_verify()` in `launcher.pyw`
10. `send_helper_command()` and `start_helper_process()` in the Anki add-on

That path goes from pure functions, to APIs, to files/audio, to threading and
UI, to packaging and cross-process control.
