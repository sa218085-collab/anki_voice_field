# Project Phases

## Phase 1: External Helper

Phase 1 is the working external Python app in the project root.

Use it with:

```powershell
python main.py --dry-run
python main.py
```

Or double-click:

```text
start_anki_voice_field.vbs
```

Phase 1 talks to Anki through AnkiConnect. Keep this working while Phase 2 is
being built.

## Phase 2: Native Anki Add-on (v2)

Phase 2 lives in:

```text
anki_addon/anki_voice_field/
```

This folder is meant to be copied into Anki's `addons21` folder for testing.

The Phase 2 controller is embedded in Anki's reviewer:

1. A compact bottom strip displays recording state, target field, queue count,
   and the review-before-save toggle.
2. The Anki add-on locks the current card, note, and destination field before
   it asks the helper to record.
3. A headless local service records, transcribes, queues, writes, and verifies.
4. Completed transcripts open in modeless native Anki dialogs.
5. The original helper remains available as the v1 rollback path.

The external helper remains the recording/transcription engine. The package
includes its source and setup script while excluding the compiled Whisper
environment and model cache.

Install locally with:

```powershell
.\install_personal_addon.ps1
```

Package for sharing with:

```powershell
.\package_addon.ps1
```

## Checkpoint Habit

Before major changes, make a git commit.

That gives us a saved point we can return to if Phase 2 gets messy.
