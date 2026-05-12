from __future__ import annotations

import html
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import config


ANKICONNECT_HELP = (
    "Could not reach AnkiConnect. Install the AnkiConnect add-on in Anki, "
    "restart Anki, keep Anki Desktop open, and make sure AnkiConnect is "
    f"listening at {config.ANKI_CONNECT_URL}."
)


class AnkiConnectError(RuntimeError):
    pass


class MissingFieldError(RuntimeError):
    def __init__(self, required_field: str, available_fields: list[str]) -> None:
        fields = ", ".join(available_fields) if available_fields else "(none)"
        super().__init__(
            f"Could not find a usable target field. Tried: {required_field}. "
            f"Available fields: {fields}"
        )


class UpdateVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurrentNote:
    card_id: int
    note_id: int
    deck_name: str
    model_name: str
    fields: dict[str, str]


@dataclass(frozen=True)
class CurrentCard:
    card_id: int
    deck_name: str
    model_name: str
    fields: dict[str, str]


def invoke(action: str, params: dict[str, Any] | None = None) -> Any:
    payload = {
        "action": action,
        "version": 6,
        "params": params or {},
    }
    request = urllib.request.Request(
        config.ANKI_CONNECT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AnkiConnectError(ANKICONNECT_HELP) from exc

    if body.get("error"):
        raise AnkiConnectError(str(body["error"]))
    return body.get("result")


def check_connection() -> int:
    return int(invoke("version"))


def get_current_card_note() -> CurrentNote:
    card = invoke("guiCurrentCard")
    if not card:
        raise AnkiConnectError("No current reviewed card found. Open Anki's reviewer.")

    card_id = card.get("cardId")
    if card_id is None:
        raise AnkiConnectError("AnkiConnect did not return a card ID for the current card.")

    card_info = invoke("cardsInfo", {"cards": [card_id]})
    if not card_info:
        raise AnkiConnectError(f"Could not read card info for card {card_id}.")

    first_card = card_info[0]
    note_id = first_card.get("note")
    if note_id is None:
        raise AnkiConnectError(f"Could not find a note ID for card {card_id}.")

    note_info = invoke("notesInfo", {"notes": [note_id]})
    if not note_info:
        raise AnkiConnectError(f"Could not read note info for note {note_id}.")

    note = note_info[0]
    fields = {
        field_name: field_data.get("value", "")
        for field_name, field_data in note.get("fields", {}).items()
    }

    return CurrentNote(
        card_id=int(card_id),
        note_id=int(note_id),
        deck_name=str(first_card.get("deckName", "")),
        model_name=str(note.get("modelName", first_card.get("modelName", ""))),
        fields=fields,
    )


def get_current_review_card() -> CurrentCard:
    card = invoke("guiCurrentCard")
    if not card:
        raise AnkiConnectError("No current reviewed card found. Open Anki's reviewer.")

    card_id = card.get("cardId")
    if card_id is None:
        raise AnkiConnectError("AnkiConnect did not return a card ID for the current card.")

    fields = {
        field_name: field_data.get("value", "")
        for field_name, field_data in card.get("fields", {}).items()
    }

    return CurrentCard(
        card_id=int(card_id),
        deck_name=str(card.get("deckName", "")),
        model_name=str(card.get("modelName", "")),
        fields=fields,
    )


def get_current_review_card_id() -> int | None:
    card = invoke("guiCurrentCard")
    if not card:
        return None

    card_id = card.get("cardId")
    if card_id is None:
        return None
    return int(card_id)


def resolve_note_id_from_card(card_id: int) -> int:
    note_ids = invoke("cardsToNotes", {"cards": [card_id]})
    if not note_ids:
        raise AnkiConnectError(f"Could not find a note ID for card {card_id}.")
    return int(note_ids[0])


def require_field(note: CurrentNote, field_name: str) -> str:
    if field_name not in note.fields:
        raise MissingFieldError(field_name, list(note.fields.keys()))
    return note.fields[field_name]


def require_field_in_fields(fields: dict[str, str], field_name: str) -> str:
    if field_name not in fields:
        raise MissingFieldError(field_name, list(fields.keys()))
    return fields[field_name]


def is_image_occlusion_model(model_name: str) -> bool:
    normalized_model = model_name.casefold()
    return any(
        hint.casefold() in normalized_model
        for hint in config.IMAGE_OCCLUSION_MODEL_HINTS
    )


def choose_target_field(fields: dict[str, str], model_name: str) -> str:
    if config.TARGET_FIELD_NAME in fields:
        return config.TARGET_FIELD_NAME

    if (
        is_image_occlusion_model(model_name)
        and config.IMAGE_OCCLUSION_FALLBACK_FIELD_NAME in fields
    ):
        return config.IMAGE_OCCLUSION_FALLBACK_FIELD_NAME

    for field_name in config.DEFAULT_FALLBACK_FIELD_NAMES:
        if field_name in fields:
            return field_name

    tried_fields = [
        config.TARGET_FIELD_NAME,
        f"{config.IMAGE_OCCLUSION_FALLBACK_FIELD_NAME} (image occlusion)",
        *config.DEFAULT_FALLBACK_FIELD_NAMES,
    ]
    raise MissingFieldError(", ".join(tried_fields), list(fields.keys()))


def get_note_fields(note_id: int) -> dict[str, str]:
    note_info = invoke("notesInfo", {"notes": [note_id]})
    if not note_info:
        raise AnkiConnectError(f"Could not read note info for note {note_id}.")

    return {
        field_name: field_data.get("value", "")
        for field_name, field_data in note_info[0].get("fields", {}).items()
    }


def get_selected_browser_note_ids() -> list[int]:
    try:
        selected_notes = invoke("guiSelectedNotes")
    except AnkiConnectError:
        return []

    return [int(note_id) for note_id in selected_notes or []]


def transcript_to_html(transcript: str) -> str:
    lines = transcript.strip().splitlines()
    return "<br>".join(html.escape(line, quote=False) for line in lines)


def build_voice_note_block(transcript: str, timestamp: datetime | None = None) -> str:
    if timestamp is None:
        timestamp = datetime.now()

    safe_transcript = transcript_to_html(transcript)
    if not safe_transcript:
        raise ValueError("Transcript is empty.")

    stamp = timestamp.strftime("%Y-%m-%d %H:%M")
    return f"<hr>\n<b>Voice Note - {stamp}</b><br>\n{safe_transcript}"


def append_transcript_to_field(
    existing_field_html: str,
    transcript: str,
    timestamp: datetime | None = None,
) -> str:
    block = build_voice_note_block(transcript, timestamp)
    if not existing_field_html:
        return block
    return f"{existing_field_html}\n{block}"


def field_contains_appended_transcript(
    field_html: str,
    transcript: str,
    timestamp: datetime,
) -> bool:
    stamp = timestamp.strftime("%Y-%m-%d %H:%M")
    if f"Voice Note - {stamp}" not in field_html:
        return False

    for line in transcript.strip().splitlines():
        safe_line = html.escape(line.strip(), quote=False)
        if safe_line and safe_line not in field_html:
            return False

    return True


def update_note_field(note_id: int, field_name: str, updated_value: str) -> None:
    invoke(
        "updateNoteFields",
        {
            "note": {
                "id": note_id,
                "fields": {
                    field_name: updated_value,
                },
            }
        },
    )
