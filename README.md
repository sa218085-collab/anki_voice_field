# anki_voice_field

Minimal external Python script for appending a spoken note to the currently
reviewed Anki card's note field.

This is not a native Anki add-on. It talks to Anki Desktop through AnkiConnect at
`http://localhost:8765`.

## Safety Rules

- Only reads the current reviewer card.
- Only updates that current card's note.
- Prefers the field named exactly `Lecture Notes`.
- If `Lecture Notes` is missing, uses a fallback field instead of stopping.
- Never overwrites the field; it appends to the bottom.
- Stops with a clear error if no usable target field exists.
- Supports `--dry-run` so you can preview before writing.
- Does not create new cards.
- Does not bulk edit cards.

## Install

Install Anki Desktop and the AnkiConnect add-on first. Keep Anki open.

Then install Python dependencies:

```powershell
cd "D:\Computer Science\projects\python\anki_voice_field"
pip install -r requirements.txt
```

This MVP uses `faster-whisper` for local speech-to-text. It does not require a
paid cloud API. The first transcription may download a Whisper model. The model
size is configured in `config.py`.

## Test AnkiConnect Only

Use this before recording audio:

```powershell
python main.py --test-anki
```

It checks AnkiConnect and prints current card/note information if Anki is in the
reviewer.

## Dry Run

This records and transcribes, but does not write to Anki:

```powershell
python main.py --dry-run
```

Use this first. It prints the updated field preview.

## Real Run

This records, transcribes, and appends to the chosen target field on the current
card's note:

```powershell
python main.py
```

Press `F8` to start recording. Press `F8` again to stop.

The command-line script locks the target note before recording, so after you
stop recording you may move to another card while transcription finishes.

## Run Without PowerShell

For normal daily use, double-click:

```text
start_anki_voice_field.vbs
```

That starts the helper minimized without a PowerShell terminal. The global `F8`
hotkey still works while you are reviewing cards in Anki, so you do not need to
click out of Anki.

If you want to see the status window immediately, double-click:

```text
open_status_window.vbs
```

The window lets you:

- test the current Anki card
- toggle dry-run mode
- toggle review mode vs fast mode
- start/stop recording with the button or `F8`
- see transcripts, errors, and verified write messages

The helper locks onto the current card/note when recording starts. After it
transcribes, it re-reads that same note, appends to the chosen target field,
writes the field, and verifies the write by reading it back.

## Target Field Fallback

The helper chooses where to put the voice note in this order:

1. `Lecture Notes`, if that field exists.
2. `Remarks`, if the note type looks like Image Occlusion and `Remarks` exists.
3. `Back`, then `Extra`, then `Back Extra`, then `Remarks`.

If none of those fields exist, it stops and lists the available fields. This
keeps the app from guessing wildly or editing the wrong place.

For speed, the microphone starts immediately when you press `F8`. The helper
locks the current Anki card in the background while you are speaking. For best
safety, press `F8` while the correct card is visible and do not advance until
you stop that recording.

When it is time to write, the helper checks whether Anki is still showing the
same target card. If it is, the helper waits briefly for you to move off that
card before saving. This avoids a reviewer timing issue where Anki can overwrite
an external field update after you answer the card.

By default, that wait only applies to risky fallback fields like `Remarks`.
Regular `Lecture Notes` saves do not require moving to the next card first.

That means you can press `F8` to stop recording and then move to the next Anki
card while transcription finishes. The note that gets updated is the original
card's note, not whichever card you are viewing later.

After transcription, the helper shows a review popup before writing. You can:

- edit the transcript and click `Save To Anki`
- click `Re-record` to discard it and speak again for the same locked note
- click `Cancel` to write nothing

The transcript is not written when the popup first appears. The write happens
only when you click `Save To Anki`.

After you click `Save To Anki`, the helper may retry the Anki write internally
before it reports success or failure. This handles Anki taking a few seconds to
persist the field update.

If saving still fails with a message about read-back verification, close Anki
Browser or any note editor window showing that note, then click `Save To Anki`
again. AnkiConnect can silently refuse field updates for notes currently open in
the Browser/editor.

## Review Mode vs Fast Mode

The helper has two save modes:

Review mode:

- `Review before saving` is checked.
- After transcription, an editable popup appears.
- You can edit, re-record, cancel, or click `Save To Anki`.
- This is safest.

Fast mode:

- `Review before saving` is unchecked.
- After transcription, the helper automatically appends to Anki.
- A read-only transcript confirmation appears after the verified save.
- This is fastest.

Dry run still never writes to Anki, regardless of mode.

The locked note does not change when you re-record. That means if you stopped
recording on card A and moved to card B, re-recording still targets card A's
note.

After a verified append, a small transcript confirmation appears so you can
quickly check what was saved. You can turn this off in `config.py` with
`SHOW_TRANSCRIPT_POPUP = False`.

The Whisper model is loaded in the background when the helper starts. The first
load can still take a moment, but later notes should be faster because the model
is reused instead of loaded from scratch.

## Queue Behavior

The status-window helper supports a simple queue.

Each time you stop recording, the helper:

1. saves that recording to its own temporary audio file
2. remembers the card/note that was locked when recording started
3. puts the audio into a background transcription queue
4. immediately lets you record another card

The queue processes one recording at a time. This keeps the local Whisper model
stable while still letting you continue reviewing quickly.

If several transcripts finish, you may get several review popups. Each popup is
tied to the note that was locked for that recording.

## Voice Notes Backup Log

Every successful save is also written to:

```text
voice_notes_log.txt
```

Each entry includes:

- saved date/time
- card ID
- note ID
- transcript text

The backup log is only written after Anki has been updated and verified. Failed,
canceled, and dry-run transcripts are not added to this file.

## Native Anki Add-on Later

This MVP is still an external helper. Turning it into a native Anki add-on is
possible, but local Whisper and microphone dependencies are harder to package
inside Anki's Python environment. The external helper is simpler and safer for
the first working version.

Phase 2 has started in:

```text
anki_addon/anki_voice_field/
```

The personal native add-on now works as a controller for the external helper.
It adds Anki Tools menu actions and an Anki-local hotkey that send commands to
the helper's local control server.

To install the personal add-on locally:

```powershell
.\install_personal_addon.ps1
```

Then restart Anki and use:

```text
Tools > Anki Voice Field: Record / Stop
```

When the add-on starts the helper, it uses `--disable-global-hotkey` so Anki owns
`F8` and the helper does not also catch the same key press.

## Beginner Notes

Read `BEGINNER_NOTES.py` for a guided explanation of the project. It uses Python
triple-quoted `''' ... '''` blocks to explain the code and the computer science
concepts behind it.

## Append Format

Each voice note is appended like this:

```html
<hr>
<b>Voice Note - YYYY-MM-DD HH:MM</b><br>
transcribed text here
```

## Run Tests

```powershell
python -m unittest discover -s tests
```

The test checks the field append behavior.

## Files

- `config.py`: configurable values like target fields, hotkey, AnkiConnect URL,
  dry-run default, and audio temp path.
- `anki_client.py`: safe AnkiConnect calls, target field selection, and append
  formatting.
- `recorder.py`: push-to-talk microphone recording and unique temp audio files.
- `transcriber.py`: local transcription using `faster-whisper`.
- `main.py`: command-line flow and hotkey workflow.
- `launcher.pyw`: no-PowerShell status window, global hotkey, and queue workflow.
- `session_log.py`: writes successfully saved voice notes to `voice_notes_log.txt`.
- `tests/test_append_format.py`: unit tests for append formatting.

## What To Study First

If you are learning Python, start here:

1. `tests/test_append_format.py`
2. `append_transcript_to_field()` in `anki_client.py`
3. `get_current_card_note()` in `anki_client.py`
4. `record_once_with_hotkey()` in `main.py`
5. `transcribe_audio()` in `transcriber.py`

Those pieces teach pure functions, HTTP APIs, event-driven input, files, and
third-party packages.
