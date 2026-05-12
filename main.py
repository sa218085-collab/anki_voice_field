from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import config
from anki_client import (
    AnkiConnectError,
    MissingFieldError,
    UpdateVerificationError,
    append_transcript_to_field,
    choose_target_field,
    check_connection,
    field_contains_appended_transcript,
    get_current_card_note,
    get_current_review_card_id,
    get_note_fields,
    get_selected_browser_note_ids,
    update_note_field,
)
from session_log import append_saved_voice_note
from single_instance import acquire_instance_lock
from transcriber import TranscriptionError, transcribe_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append a voice transcript to the current Anki card's note field."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=config.DRY_RUN_DEFAULT,
        help="Show what would be written without changing Anki.",
    )
    parser.add_argument(
        "--test-anki",
        action="store_true",
        help="Only check AnkiConnect and print current card/note info.",
    )
    return parser


def print_anki_test() -> None:
    version = check_connection()
    print(f"AnkiConnect reachable. Version: {version}")

    try:
        note = get_current_card_note()
    except AnkiConnectError as exc:
        print(f"No current card/note info available: {exc}")
        return

    print(f"Current card ID: {note.card_id}")
    print(f"Current note ID: {note.note_id}")
    print(f"Deck: {note.deck_name}")
    print(f"Note type: {note.model_name}")
    print("Fields:")
    for field_name in note.fields:
        print(f"- {field_name}")


def record_once_with_hotkey() -> Path:
    try:
        from pynput import keyboard
        from recorder import Recorder
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Missing dependency: {exc.name}. Install requirements with "
            "`pip install -r requirements.txt`."
        ) from exc

    recorder = Recorder()
    finished = threading.Event()
    recorded_path: dict[str, Path] = {}
    error: dict[str, BaseException] = {}
    last_hotkey_time = 0.0

    def toggle_recording() -> None:
        nonlocal last_hotkey_time
        now = time.monotonic()
        if now - last_hotkey_time < 0.8:
            return
        last_hotkey_time = now

        try:
            if recorder.is_recording:
                recorded_path["path"] = recorder.stop()
                print("Recording stopped.")
                finished.set()
            else:
                recorder.start()
                print(f"Recording started. Press {config.HOTKEY} again to stop.")
        except BaseException as exc:
            error["error"] = exc
            finished.set()

    hotkey_name = config.HOTKEY.strip("<>").lower()
    hotkey_key = getattr(keyboard.Key, hotkey_name)

    def on_release(key) -> None:
        if key == hotkey_key:
            toggle_recording()

    print(f"Press {config.HOTKEY} to start recording.")
    with keyboard.Listener(on_release=on_release) as listener:
        finished.wait()
        listener.stop()

    if error:
        raise RuntimeError(str(error["error"])) from error["error"]
    if "path" not in recorded_path:
        raise RuntimeError("Recording did not finish.")
    return recorded_path["path"]


def preview_update(note_id: int, field_name: str, old_value: str, new_value: str) -> None:
    print("DRY RUN: Anki was not modified.")
    print(f"Note ID: {note_id}")
    print(f"Field: {field_name}")
    print("Updated field preview:")
    print(new_value)
    print(f"Characters that would be appended: {len(new_value) - len(old_value)}")


def wait_until_target_card_is_not_current(card_id: int) -> None:
    deadline = time.monotonic() + config.WAIT_FOR_TARGET_CARD_CHANGE_SECONDS
    logged_wait = False

    while time.monotonic() <= deadline:
        try:
            current_card_id = get_current_review_card_id()
        except AnkiConnectError:
            return

        if current_card_id != card_id:
            if logged_wait:
                print("Target card changed. Writing to Anki now.")
            return

        if not logged_wait:
            print(
                "Target card is still active. Move to the next card if you want "
                "the helper to save after the review action finishes."
            )
            logged_wait = True

        time.sleep(config.WAIT_FOR_TARGET_CARD_CHANGE_POLL_SECONDS)

    raise UpdateVerificationError(
        "Anki is still showing the target card. Answer or move off that card, "
        "then run/save again."
    )


def run(dry_run: bool) -> None:
    instance_lock = acquire_instance_lock()
    _ = instance_lock

    check_connection()
    note = get_current_card_note()
    field_name = choose_target_field(note.fields, note.model_name)
    print(f'Locked target card {note.card_id}, note {note.note_id}, field "{field_name}".')
    print("After stopping the recording, you may move to the next Anki card.")

    audio_path = record_once_with_hotkey()
    print("Transcribing...")
    transcript = transcribe_audio(audio_path)
    print(f"Transcript: {transcript}")

    fields = get_note_fields(note.note_id)
    if field_name not in fields:
        raise MissingFieldError(field_name, list(fields.keys()))
    existing_value = fields[field_name]
    timestamp = datetime.now()
    updated_value = append_transcript_to_field(
        existing_value,
        transcript,
        timestamp,
    )
    appended_count = len(updated_value) - len(existing_value)

    if dry_run:
        preview_update(note.note_id, field_name, existing_value, updated_value)
        return

    if note.note_id in get_selected_browser_note_ids():
        raise UpdateVerificationError(
            "This note is selected in Anki Browser. Close Browser or select a "
            "different note, then retry."
        )

    wait_until_target_card_is_not_current(note.card_id)

    verified = False
    for attempt in range(1, config.SAVE_RETRY_ATTEMPTS + 1):
        update_note_field(note.note_id, field_name, updated_value)

        deadline = time.monotonic() + config.POST_SAVE_VERIFY_TIMEOUT_SECONDS
        while time.monotonic() <= deadline:
            verified_fields = get_note_fields(note.note_id)
            verified_value = verified_fields.get(field_name, "")
            if field_contains_appended_transcript(verified_value, transcript, timestamp):
                time.sleep(config.POST_SAVE_STABLE_SECONDS)
                verified_fields = get_note_fields(note.note_id)
                verified_value = verified_fields.get(field_name, "")
                verified = field_contains_appended_transcript(
                    verified_value,
                    transcript,
                    timestamp,
                )
                break
            time.sleep(config.POST_SAVE_VERIFY_POLL_SECONDS)

        if verified:
            break

        if attempt < config.SAVE_RETRY_ATTEMPTS:
            print("Save not visible yet; retrying Anki write...")

    if not verified:
        raise UpdateVerificationError(
            "AnkiConnect accepted the update, but the field did not stay changed "
            f"after {config.SAVE_RETRY_ATTEMPTS} attempts. Close Anki Browser/editor "
            "if it is showing this note, then retry."
        )

    append_saved_voice_note(
        saved_at=datetime.now(),
        card_id=note.card_id,
        note_id=note.note_id,
        field_name=field_name,
        transcript=transcript,
    )
    print(
        f"Updated note {note.note_id}. "
        f'Verified append of {appended_count} characters to "{field_name}".'
    )


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.test_anki:
            print_anki_test()
        else:
            run(dry_run=args.dry_run)
    except MissingFieldError as exc:
        print(f"Field error: {exc}")
        return 1
    except (AnkiConnectError, TranscriptionError, UpdateVerificationError, RuntimeError) as exc:
        print(f"Error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
