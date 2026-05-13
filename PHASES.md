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

## Phase 2: Native Anki Add-on

Phase 2 lives in:

```text
anki_addon/anki_voice_field/
```

This folder is meant to be copied into Anki's `addons21` folder for testing.

The first Phase 2 milestone is a personal-use controller:

1. Load inside Anki.
2. Add a Tools menu action.
3. Add an Anki-local hotkey.
4. Start/show the external helper.
5. Send toggle/test commands to the helper over localhost.

The external helper remains the recording/transcription engine. The packaged
add-on includes the helper source and a setup script, while avoiding bundling
hundreds of megabytes of compiled Whisper dependencies directly inside Anki's
Python environment.

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
