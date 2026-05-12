from __future__ import annotations

from datetime import datetime

import config


def append_saved_voice_note(
    *,
    saved_at: datetime,
    card_id: int | None,
    note_id: int,
    field_name: str,
    transcript: str,
) -> None:
    config.VOICE_NOTES_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    timestamp = saved_at.strftime("%Y-%m-%d %H:%M:%S")
    divider = "=" * 72
    card_text = str(card_id) if card_id is not None else "unknown"

    entry = (
        f"{divider}\n"
        f"Saved: {timestamp}\n"
        f"Card ID: {card_text}\n"
        f"Note ID: {note_id}\n"
        f"Field: {field_name}\n"
        f"Transcript:\n"
        f"{transcript.strip()}\n\n"
    )

    with config.VOICE_NOTES_LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(entry)
