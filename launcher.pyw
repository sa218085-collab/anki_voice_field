from __future__ import annotations

import argparse
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

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
    get_current_review_card,
    get_current_review_card_id,
    get_note_fields,
    get_selected_browser_note_ids,
    resolve_note_id_from_card,
    update_note_field,
)
from control_server import start_control_server
from recorder import Recorder
from session_log import append_saved_voice_note
from single_instance import acquire_instance_lock
from transcriber import TranscriptionError, preload_model, transcribe_audio


@dataclass(frozen=True)
class VoiceJob:
    audio_path: Path
    card_id: int | None
    note_id: int | None
    field_name: str
    dry_run: bool
    review_before_write: bool


class VoiceFieldApp:
    def __init__(self, root: tk.Tk, *, enable_global_hotkey: bool = True) -> None:
        self.root = root
        self.root.title("Anki Voice Field")
        self.root.geometry("780x430")

        self.events: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self.recorder = Recorder()
        self.job_queue: queue.Queue[VoiceJob] = queue.Queue()
        self.target_note_id: int | None = None
        self.target_card_id: int | None = None
        self.target_field_name: str | None = None
        self.lock_event = threading.Event()
        self.lock_error: BaseException | None = None
        self.anki_write_lock = threading.Lock()
        self.is_busy = False
        self.review_count = 0
        self.hotkey_listener = None
        self.control_server = None
        self.last_hotkey_time = 0.0

        self.dry_run = tk.BooleanVar(value=config.DRY_RUN_DEFAULT)
        self.review_before_write = tk.BooleanVar(
            value=config.REVIEW_TRANSCRIPT_BEFORE_WRITE_DEFAULT
        )
        self.status = tk.StringVar(value="Ready. Press F8 to record.")

        self._build_ui()
        if enable_global_hotkey:
            self._start_hotkey_listener()
        else:
            self.log("Global hotkey disabled. Use the Anki add-on hotkey/menu.")
        self._start_control_server()
        threading.Thread(target=self._job_worker, daemon=True).start()
        self._check_events()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.log("Anki Voice Field is ready.")
        self.log(f"Hotkey: {config.HOTKEY}")
        self.log(f"Primary target field: {config.TARGET_FIELD_NAME}")
        self.log("Fallback fields enabled: image occlusion -> Remarks; otherwise Back/Extra.")
        if config.PRELOAD_WHISPER_MODEL:
            self.log("Loading speech model in the background for faster notes.")
            threading.Thread(target=self._preload_model_worker, daemon=True).start()

    def _start_control_server(self) -> None:
        try:
            self.control_server, _thread = start_control_server(
                config.CONTROL_SERVER_HOST,
                config.CONTROL_SERVER_PORT,
                on_toggle=self._control_toggle_recording,
                on_show=self._control_show_window,
                on_test_anki=self._control_test_anki,
            )
        except OSError as exc:
            self.log(f"Control server could not start: {exc}")
            return

        self.log(
            "Control server ready at "
            f"http://{config.CONTROL_SERVER_HOST}:{config.CONTROL_SERVER_PORT}."
        )

    def _control_toggle_recording(self) -> dict[str, object]:
        self.root.after(0, self.toggle_recording)
        return {"message": "Toggle recording queued."}

    def _control_show_window(self) -> dict[str, object]:
        def show() -> None:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        self.root.after(0, show)
        return {"message": "Show window queued."}

    def _control_test_anki(self) -> dict[str, object]:
        self.root.after(0, self.test_anki)
        return {"message": "Test Anki queued."}

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=14, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, textvariable=self.status, font=("Segoe UI", 12, "bold")).pack(
            anchor="w"
        )

        controls = tk.Frame(frame)
        controls.pack(fill=tk.X, pady=(10, 8))

        self.toggle_button = tk.Button(
            controls,
            text="Start Recording",
            width=18,
            command=self.toggle_recording,
        )
        self.toggle_button.pack(side=tk.LEFT)

        self.test_button = tk.Button(
            controls,
            text="Test Anki",
            width=14,
            command=self.test_anki,
        )
        self.test_button.pack(side=tk.LEFT, padx=(8, 0))

        tk.Checkbutton(
            controls,
            text="Dry run",
            variable=self.dry_run,
        ).pack(side=tk.LEFT, padx=(14, 0))

        tk.Checkbutton(
            controls,
            text="Review before saving",
            variable=self.review_before_write,
        ).pack(side=tk.LEFT, padx=(14, 0))

        self.log_box = ScrolledText(frame, height=18, wrap=tk.WORD)
        self.log_box.pack(fill=tk.BOTH, expand=True)
        self.log_box.configure(state=tk.DISABLED)

    def _start_hotkey_listener(self) -> None:
        try:
            from pynput import keyboard
        except ModuleNotFoundError:
            self.log("Missing dependency: pynput. Run pip install -r requirements.txt")
            return

        hotkey_name = config.HOTKEY.strip("<>").lower()
        hotkey_key = getattr(keyboard.Key, hotkey_name)

        def on_release(key) -> None:
            if key == hotkey_key:
                self.events.put(("toggle", None))

        self.hotkey_listener = keyboard.Listener(on_release=on_release)
        self.hotkey_listener.start()

    def _check_events(self) -> None:
        while not self.events.empty():
            event_name, payload = self.events.get()
            if event_name == "toggle":
                self.toggle_recording()
            elif event_name == "log":
                self.log(str(payload))
            elif event_name == "status":
                self.status.set(str(payload))
            elif event_name == "busy":
                self.is_busy = bool(payload)
                self._update_buttons()
            elif event_name == "transcript_popup":
                self.show_transcript_popup(payload)
            elif event_name == "review_transcript":
                self.show_review_popup(payload)
            elif event_name == "queue_status":
                self.update_queue_status()

        self.root.after(100, self._check_events)

    def _update_buttons(self) -> None:
        if self.is_busy:
            self.toggle_button.configure(state=tk.DISABLED)
            self.test_button.configure(state=tk.DISABLED)
            return

        self.test_button.configure(state=tk.NORMAL)
        if self.recorder.is_recording:
            self.toggle_button.configure(text="Stop Recording", state=tk.NORMAL)
        else:
            self.toggle_button.configure(text="Start Recording", state=tk.NORMAL)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with config.LOG_FILE.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {message}\n")

        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"{message}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def update_queue_status(self) -> None:
        queued = self.job_queue.qsize()
        if self.recorder.is_recording:
            return
        if queued:
            self.status.set(f"{queued} voice note(s) queued. Ready to record another.")
        elif self.review_count:
            self.status.set(f"{self.review_count} transcript(s) waiting for review.")
        else:
            self.status.set("Ready. Press F8 to record.")

    def _preload_model_worker(self) -> None:
        try:
            preload_model()
        except TranscriptionError as exc:
            self.events.put(("log", f"Speech model preload failed: {exc}"))
        else:
            self.events.put(("log", "Speech model loaded. Future notes should be faster."))

    def show_transcript_popup(self, payload: object | None) -> None:
        if not config.SHOW_TRANSCRIPT_POPUP or not isinstance(payload, dict):
            return

        popup = tk.Toplevel(self.root)
        popup.title("Voice Note Transcript")
        popup.geometry("560x260+80+80")
        popup.attributes("-topmost", True)

        status = str(payload.get("status", "Voice note complete"))
        note_id = str(payload.get("note_id", "unknown"))
        card_id = str(payload.get("card_id", "unknown"))
        field_name = str(payload.get("field_name", "unknown"))
        transcript = str(payload.get("transcript", ""))

        frame = tk.Frame(popup, padx=12, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=status, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(frame, text=f"Card {card_id} | Note {note_id}").pack(anchor="w")
        tk.Label(frame, text=f"Field: {field_name}").pack(anchor="w")

        text_box = ScrolledText(frame, height=8, wrap=tk.WORD)
        text_box.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        text_box.insert(tk.END, transcript)
        text_box.configure(state=tk.DISABLED)

        tk.Button(frame, text="Close", command=popup.destroy).pack(anchor="e")
        popup.after(config.TRANSCRIPT_POPUP_SECONDS * 1000, popup.destroy)

    def show_review_popup(self, payload: object | None) -> None:
        if not isinstance(payload, dict):
            return

        note_id = int(payload["note_id"])
        card_id = payload.get("card_id")
        field_name = str(payload.get("field_name", config.TARGET_FIELD_NAME))
        transcript = str(payload.get("transcript", ""))
        dry_run = bool(payload.get("dry_run", False))

        self.review_count += 1
        self._update_buttons()
        self.log(
            f'Review popup opened for note {note_id}, field "{field_name}". '
            "Anki will not be modified until you click Save To Anki."
        )

        popup = tk.Toplevel(self.root)
        popup.title("Review Voice Note")
        popup.geometry("640x360+80+80")
        popup.attributes("-topmost", True)

        frame = tk.Frame(popup, padx=12, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        mode = "Dry run preview" if dry_run else "Review before appending"
        tk.Label(frame, text=mode, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(frame, text=f"Card {card_id} | Note {note_id}").pack(anchor="w")
        tk.Label(frame, text=f'Field: {field_name}').pack(anchor="w")
        tk.Label(
            frame,
            text="Edit the transcript if needed, then click Save To Anki to write it.",
        ).pack(anchor="w")

        text_box = ScrolledText(frame, height=11, wrap=tk.WORD)
        text_box.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        text_box.insert(tk.END, transcript)
        text_box.focus_set()

        buttons = tk.Frame(frame)
        buttons.pack(fill=tk.X)

        def close_review(status_message: str) -> None:
            self.review_count = max(0, self.review_count - 1)
            self.status.set(status_message)
            self.update_queue_status()
            self._update_buttons()
            popup.destroy()

        def save_edit() -> None:
            corrected = text_box.get("1.0", tk.END).strip()
            if not corrected:
                self.log("Cannot save an empty transcript.")
                return

            if dry_run:
                self.log("DRY RUN: edited transcript was not written to Anki.")
                self.log(f"Edited transcript: {corrected}")
                close_review("Dry run reviewed. Ready for next note.")
                return

            close_review("Saving corrected transcript...")
            self.log(f'Saving reviewed transcript to note {note_id}, field "{field_name}".')
            threading.Thread(
                target=self._append_reviewed_transcript_worker,
                args=(note_id, card_id, field_name, corrected),
                daemon=True,
            ).start()

        def rerecord() -> None:
            close_review("Re-recording for the same locked note.")
            try:
                self.start_recording_for_locked_note(note_id, card_id, field_name)
            except RuntimeError as exc:
                self.log(f"Could not re-record: {exc}")
                self.status.set("Could not re-record. See log.")

        def cancel() -> None:
            self.log(f"Canceled transcript for note {note_id}; Anki was not modified.")
            close_review("Transcript canceled. Ready for next note.")

        save_text = "Close Dry Run" if dry_run else "Save To Anki"
        tk.Button(buttons, text=save_text, width=16, command=save_edit).pack(
            side=tk.LEFT
        )
        tk.Button(buttons, text="Re-record", width=14, command=rerecord).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(buttons, text="Cancel", width=12, command=cancel).pack(
            side=tk.RIGHT
        )

        popup.bind("<Control-Return>", lambda _event: save_edit())
        popup.protocol("WM_DELETE_WINDOW", cancel)

    def test_anki(self) -> None:
        self.events.put(("busy", True))
        threading.Thread(target=self._test_anki_worker, daemon=True).start()

    def _test_anki_worker(self) -> None:
        try:
            version = check_connection()
            note = get_current_card_note()
            field_name = choose_target_field(note.fields, note.model_name)
        except (AnkiConnectError, MissingFieldError) as exc:
            self.events.put(("log", f"Anki test failed: {exc}"))
        else:
            self.events.put(("log", f"AnkiConnect version: {version}"))
            self.events.put(("log", f"Current card ID: {note.card_id}"))
            self.events.put(("log", f"Current note ID: {note.note_id}"))
            self.events.put(("log", f"Deck: {note.deck_name}"))
            self.events.put(("log", f"Note type: {note.model_name}"))
            self.events.put(("log", f'Will append to field: "{field_name}"'))
        finally:
            self.events.put(("busy", False))

    def toggle_recording(self) -> None:
        now = time.monotonic()
        if now - self.last_hotkey_time < 0.8:
            return
        self.last_hotkey_time = now

        self.log("Hotkey/button received.")

        if self.is_busy:
            return

        if self.recorder.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        try:
            self.start_recording_for_current_card()
        except RuntimeError as exc:
            self.log(f"Could not start recording: {exc}")
            return

    def start_recording_for_current_card(self) -> None:
        if self.recorder.is_recording:
            raise RuntimeError("Already recording.")

        self.target_note_id = None
        self.target_card_id = None
        self.target_field_name = None
        self.lock_error = None
        self.lock_event.clear()

        self.recorder.start()
        threading.Thread(target=self._lock_current_card_worker, daemon=True).start()

        self.status.set("Recording... locking current Anki card in background.")
        self.log("Recording started immediately. Locking current Anki card.")
        self._update_buttons()

    def _lock_current_card_worker(self) -> None:
        try:
            card = get_current_review_card()
            field_name = choose_target_field(card.fields, card.model_name)
            self.target_card_id = card.card_id
            self.target_field_name = field_name
            self.events.put(
                (
                    "log",
                    f'Target card locked: card {card.card_id}, field "{field_name}". '
                    "You can move after stopping.",
                )
            )
            self.events.put(("status", "Recording... target card locked."))
        except (AnkiConnectError, MissingFieldError) as exc:
            self.lock_error = exc
            self.events.put(("log", f"Could not lock current card: {exc}"))
            self.events.put(("status", "Error locking card. Stop recording."))
        finally:
            self.lock_event.set()

        if self.target_card_id is None:
            return

        try:
            self.target_note_id = resolve_note_id_from_card(self.target_card_id)
            self.events.put(("log", f"Resolved target note: {self.target_note_id}."))
        except AnkiConnectError as exc:
            self.events.put(("log", f"Could not resolve target note yet: {exc}"))

    def start_recording_for_locked_note(
        self,
        note_id: int,
        card_id: int | None,
        field_name: str | None = None,
    ) -> None:
        if self.recorder.is_recording:
            raise RuntimeError("Already recording.")

        self.target_note_id = note_id
        self.target_card_id = card_id
        self.target_field_name = field_name or config.TARGET_FIELD_NAME
        self.lock_error = None
        self.lock_event.set()
        self.recorder.start()

        self.status.set("Recording... press F8 again to stop.")
        self.log(
            f"Recording for card {self.target_card_id}, note {self.target_note_id}, "
            f'field "{self.target_field_name}".'
        )
        self.log("Target note locked. You can move to the next card after stopping.")
        self._update_buttons()

    def stop_recording(self) -> None:
        try:
            audio_path = self.recorder.stop()
        except RuntimeError as exc:
            self.log(f"Could not stop recording: {exc}")
            self._update_buttons()
            return

        if not self.lock_event.wait(timeout=10):
            self.log("Could not lock the target card before recording stopped.")
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._update_buttons()
            return

        if self.lock_error is not None:
            self.log(f"Discarding recording because target lock failed: {self.lock_error}")
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._update_buttons()
            return

        note_id = self.target_note_id
        card_id = self.target_card_id
        field_name = self.target_field_name
        if card_id is None and note_id is None:
            self.log("No target card or note was locked before recording.")
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._update_buttons()
            return

        if field_name is None:
            self.log("No target field was selected before recording stopped.")
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._update_buttons()
            return

        dry_run = self.dry_run.get()
        self.job_queue.put(
            VoiceJob(
                audio_path=audio_path,
                card_id=card_id,
                note_id=note_id,
                field_name=field_name,
                dry_run=dry_run,
                review_before_write=self.review_before_write.get(),
            )
        )
        self.log(
            f'Recording stopped. Queued card {card_id}, note {note_id or "pending"}, '
            f'field "{field_name}"; '
            "you can record the next card now."
        )
        self.update_queue_status()
        self._update_buttons()

    def _job_worker(self) -> None:
        while True:
            job = self.job_queue.get()
            self.events.put(
                (
                    "log",
                    f'Processing queued audio for card {job.card_id}, '
                    f'note {job.note_id}, field "{job.field_name}".',
                )
            )
            self.events.put(("queue_status", None))

            try:
                self._process_voice_job(job)
            finally:
                try:
                    job.audio_path.unlink(missing_ok=True)
                except OSError:
                    pass
                self.job_queue.task_done()
                self.events.put(("queue_status", None))

    def _process_voice_job(self, job: VoiceJob) -> None:
        try:
            note_id = job.note_id
            transcript: str | None = None
            if note_id is None:
                if job.card_id is None:
                    raise AnkiConnectError("Queued recording has no locked card ID.")
                note_id = resolve_note_id_from_card(job.card_id)

            transcript = transcribe_audio(job.audio_path)
            self.events.put(("log", f"Transcript: {transcript}"))

            if job.review_before_write:
                self.events.put(
                    (
                        "review_transcript",
                        {
                            "card_id": job.card_id,
                            "note_id": note_id,
                            "field_name": job.field_name,
                            "transcript": transcript,
                            "dry_run": job.dry_run,
                        },
                    )
                )
                self.events.put(("status", "Review transcript before saving."))
                return

            fields = get_note_fields(note_id)
            if job.field_name not in fields:
                raise MissingFieldError(job.field_name, list(fields.keys()))

            existing_value = fields[job.field_name]
            timestamp = datetime.now()
            updated_value = append_transcript_to_field(
                existing_value,
                transcript,
                timestamp,
            )
            appended_count = len(updated_value) - len(existing_value)

            if job.dry_run:
                self.events.put(("log", "DRY RUN: Anki was not modified."))
                self.events.put(("log", "Updated field preview:"))
                self.events.put(("log", updated_value))
                self.events.put(
                    ("status", f"Dry run complete. {appended_count} chars previewed.")
                )
                self.events.put(
                    (
                        "transcript_popup",
                        {
                            "status": "Dry run transcript preview",
                            "card_id": job.card_id,
                            "note_id": note_id,
                            "transcript": transcript,
                        },
                    )
                )
                return

            self._write_and_verify(
                note_id,
                job.card_id,
                job.field_name,
                updated_value,
                transcript,
                timestamp,
            )

            append_saved_voice_note(
                saved_at=datetime.now(),
                card_id=job.card_id,
                note_id=note_id,
                field_name=job.field_name,
                transcript=transcript,
            )
            self.events.put(
                (
                    "log",
                    f'Updated note {note_id}. Verified append of {appended_count} '
                    f'chars to "{job.field_name}".',
                )
            )
            self.events.put(("status", "Append verified. Ready for next note."))
            self.events.put(
                (
                    "transcript_popup",
                    {
                        "status": f"Appended {appended_count} characters",
                        "card_id": job.card_id,
                        "note_id": note_id,
                        "field_name": job.field_name,
                        "transcript": transcript,
                    },
                )
            )
        except UpdateVerificationError as exc:
            self.events.put(("log", f"Save failed: {exc}"))
            self.events.put(("status", "Save paused. Move off target card and retry."))
            if transcript and note_id is not None:
                self.events.put(
                    (
                        "review_transcript",
                        {
                            "card_id": job.card_id,
                            "note_id": note_id,
                            "field_name": job.field_name,
                            "transcript": transcript,
                            "dry_run": False,
                        },
                    )
                )
            return
        except (AnkiConnectError, MissingFieldError, TranscriptionError, RuntimeError) as exc:
            self.events.put(("log", f"Error: {exc}"))
            self.events.put(("status", "Error. See log."))

    def _append_reviewed_transcript_worker(
        self,
        note_id: int,
        card_id: int | None,
        field_name: str,
        transcript: str,
    ) -> None:
        try:
            fields = get_note_fields(note_id)
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

            self._write_and_verify(
                note_id,
                card_id,
                field_name,
                updated_value,
                transcript,
                timestamp,
            )

            append_saved_voice_note(
                saved_at=datetime.now(),
                card_id=card_id,
                note_id=note_id,
                field_name=field_name,
                transcript=transcript,
            )
            self.events.put(
                (
                    "log",
                    f'Updated note {note_id}. Verified append of {appended_count} '
                    f'chars to "{field_name}".',
                )
            )
            self.events.put(("status", "Append verified. Ready for next note."))
            self.events.put(
                (
                    "transcript_popup",
                    {
                        "status": f"Appended {appended_count} characters",
                        "card_id": card_id,
                        "note_id": note_id,
                        "field_name": field_name,
                        "transcript": transcript,
                    },
                )
            )
        except UpdateVerificationError as exc:
            self.events.put(("log", f"Save failed: {exc}"))
            self.events.put(("status", "Save failed. Close Browser/editor and retry."))
            self.events.put(
                (
                    "review_transcript",
                    {
                        "card_id": card_id,
                        "note_id": note_id,
                        "field_name": field_name,
                        "transcript": transcript,
                        "dry_run": False,
                    },
                )
            )
        except (AnkiConnectError, MissingFieldError, RuntimeError) as exc:
            self.events.put(("log", f"Error: {exc}"))
            self.events.put(("status", "Error. See log."))
        finally:
            self.events.put(("busy", False))

    def _write_and_verify(
        self,
        note_id: int,
        card_id: int | None,
        field_name: str,
        updated_value: str,
        transcript: str,
        timestamp: datetime,
    ) -> None:
        with self.anki_write_lock:
            if note_id in get_selected_browser_note_ids():
                raise UpdateVerificationError(
                    "This note is selected in Anki Browser. AnkiConnect may "
                    "silently refuse field updates for a note currently open "
                    "in the Browser/editor. Close Browser or select a different "
                    "note, then retry Save To Anki."
                )

            if self._field_requires_card_change_before_save(field_name):
                self._wait_until_target_card_is_not_current(card_id)

            for attempt in range(1, config.SAVE_RETRY_ATTEMPTS + 1):
                self.events.put(
                    (
                        "log",
                        f"Save attempt {attempt}/{config.SAVE_RETRY_ATTEMPTS} "
                        f"for note {note_id}.",
                    )
                )
                update_note_field(note_id, field_name, updated_value)

                if self._wait_for_verified_append(note_id, field_name, transcript, timestamp):
                    return

                if attempt < config.SAVE_RETRY_ATTEMPTS:
                    self.events.put(
                        (
                            "log",
                            "Verification did not see the transcript yet; retrying "
                            "the Anki write automatically.",
                        )
                    )

        raise UpdateVerificationError(
            "Anki accepted the write request, but the field did not stay changed "
            f"after {config.SAVE_RETRY_ATTEMPTS} attempts. Close Anki Browser/editor "
            "if it is open, then retry Save To Anki."
        )

    def _field_requires_card_change_before_save(self, field_name: str) -> bool:
        required_fields = {
            configured_field.casefold()
            for configured_field in config.FIELDS_THAT_REQUIRE_CARD_CHANGE_BEFORE_SAVE
        }
        return field_name.casefold() in required_fields

    def _wait_until_target_card_is_not_current(self, card_id: int | None) -> None:
        if card_id is None:
            return

        deadline = time.monotonic() + config.WAIT_FOR_TARGET_CARD_CHANGE_SECONDS
        logged_wait = False

        while time.monotonic() <= deadline:
            try:
                current_card_id = get_current_review_card_id()
            except AnkiConnectError:
                return

            if current_card_id != card_id:
                if logged_wait:
                    self.events.put(("log", "Target card changed. Writing to Anki now."))
                return

            if not logged_wait:
                self.events.put(
                    (
                        "log",
                        "Target card is still active in the reviewer. Waiting briefly "
                        "before writing so Anki does not overwrite the field update.",
                    )
                )
                self.events.put(("status", "Waiting for card change before saving."))
                logged_wait = True

            time.sleep(config.WAIT_FOR_TARGET_CARD_CHANGE_POLL_SECONDS)

        self.events.put(
            (
                "log",
                "Target card is still active. Save paused so Anki does not overwrite "
                "the field update.",
            )
        )
        raise UpdateVerificationError(
            "Anki is still showing the target card. Answer or move off that card, "
            "then retry Save To Anki."
        )

    def _wait_for_verified_append(
        self,
        note_id: int,
        field_name: str,
        transcript: str,
        timestamp: datetime,
    ) -> bool:
        deadline = time.monotonic() + config.POST_SAVE_VERIFY_TIMEOUT_SECONDS

        while time.monotonic() <= deadline:
            verified_value = get_note_fields(note_id).get(field_name, "")
            if field_contains_appended_transcript(verified_value, transcript, timestamp):
                time.sleep(config.POST_SAVE_STABLE_SECONDS)
                verified_value = get_note_fields(note_id).get(field_name, "")
                if not field_contains_appended_transcript(
                    verified_value,
                    transcript,
                    timestamp,
                ):
                    return False
                return True
            time.sleep(config.POST_SAVE_VERIFY_POLL_SECONDS)

        return False

    def close(self) -> None:
        if self.recorder.is_recording:
            try:
                self.recorder.stop()
            except RuntimeError:
                pass

        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()

        if self.control_server is not None:
            self.control_server.shutdown()
            self.control_server.server_close()

        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start-minimized",
        action="store_true",
        help="Start minimized so Anki keeps your attention.",
    )
    parser.add_argument(
        "--disable-global-hotkey",
        action="store_true",
        help="Let the native Anki add-on own the hotkey.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        instance_lock = acquire_instance_lock()
    except RuntimeError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Anki Voice Field", str(exc))
        root.destroy()
        return

    root = tk.Tk()
    root.instance_lock = instance_lock
    VoiceFieldApp(root, enable_global_hotkey=not args.disable_global_hotkey)
    if args.start_minimized:
        root.after(250, root.iconify)
    root.mainloop()


if __name__ == "__main__":
    main()
