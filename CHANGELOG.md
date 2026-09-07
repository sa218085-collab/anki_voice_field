# Changelog

## 2.0.0

- Embed Record/Stop, status, target field, queue count, and review mode in the
  Anki reviewer bottom bar.
- Add modeless native transcript review, re-record, cancel, and recovery flows.
- Add a native Add-ons Config panel with recording controls, helper/model
  status, review and dry-run settings, field rules, and recent activity.
- Remove redundant Anki Tools menu commands; use the reviewer strip, F8, and
  Add-ons Config panel instead.
- Lock the card, note, and field synchronously when recording starts.
- Move the recording pipeline into a headless, loopback-only v2 service with
  explicit jobs, FIFO review order, event cursors, and protocol detection.
- Retain the legacy helper workflow as an optional client and v1 rollback path.
- Preserve the helper environment, configuration, and logs during personal
  installs.
- Add Windows CI, package verification, and service/UI coordination tests.

## 1.0.0

- Preserve the original external Tkinter helper, F8 workflow, local medical
  Whisper transcription, safe field fallback rules, verified append, and backup
  log at Git tag `v1.0.0`.
