# Anki Voice Field v2 Add-on

This add-on embeds a voice-note control strip in Anki 25.09.4's reviewer and
uses a loopback-only headless helper for microphone capture and local Whisper
transcription.

## Daily Workflow

1. Start reviewing a card.
2. Press `F8` or click `Record` in the reviewer strip.
3. Speak, then press `F8` again.
4. Continue reviewing while the FIFO queue transcribes the audio.
5. Edit and save the transcript in the modeless Anki dialog, or disable
   `Review` in the strip for verified automatic saving.

The add-on resolves `Lecture Notes` first, then Image Occlusion `Remarks`, then
`Back`, `Extra`, `Back Extra`, or `Remarks`. The selected card, note, and field
are locked at recording start.

## Architecture

- `controller.py` owns hooks, the reviewer strip bridge, hotkey, polling, and
  helper lifecycle.
- `review_dialog.py` provides the native modeless transcript editor.
- `web/` contains the responsive light/dark reviewer UI.
- `helper/headless.pyw` starts the versioned v2 service.
- `helper/legacy_client.pyw` is an optional troubleshooting UI.

All helper requests run through Anki's non-collection background executor.
Only UI updates and dialogs return to the main thread.

## Install and Package

From the project root:

```powershell
.\install_personal_addon.ps1
.\package_addon.ps1
python scripts\verify_package.py dist\anki_voice_field-v2.0.0.ankiaddon
```

The personal installer preserves the helper environment, configuration, and
logs. The packaged add-on intentionally excludes those runtime files.
