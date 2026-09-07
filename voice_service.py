from __future__ import annotations

import queue
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import config
from anki_client import (
    AnkiConnectError,
    CurrentCard,
    MissingFieldError,
    UpdateVerificationError,
    append_transcript_to_field,
    choose_target_field,
    field_contains_appended_transcript,
    get_current_review_card,
    get_current_review_card_id,
    get_note_fields,
    get_selected_browser_note_ids,
    resolve_note_id_from_card,
    update_note_field,
)
from control_server import ControlHTTPError, ControlRequest
from session_log import append_saved_voice_note


PROTOCOL_VERSION = 2
ACTIVE_JOB_STATES = {
    "queued",
    "transcribing",
    "awaiting_review",
    "rerecording",
    "saving",
    "error",
}
REVIEW_JOB_STATES = {"awaiting_review", "error"}


def _make_recorder() -> Any:
    from recorder import Recorder

    return Recorder()


def _transcribe_audio(audio_path: Path) -> str:
    from transcriber import transcribe_audio

    return transcribe_audio(audio_path)


def _preload_model() -> None:
    from transcriber import preload_model

    preload_model()


def _write_helper_log(message: str) -> None:
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with config.LOG_FILE.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{stamp}] {message}\n")


@dataclass(frozen=True)
class TargetSnapshot:
    card_id: int | None
    note_id: int | None
    field_name: str
    deck_name: str = ""
    label: str = ""

    @classmethod
    def from_payload(cls, payload: object) -> "TargetSnapshot":
        if not isinstance(payload, dict):
            raise ControlHTTPError(400, "target must be a JSON object.")

        card_id = _optional_int(payload.get("card_id"), "target.card_id")
        note_id = _optional_int(payload.get("note_id"), "target.note_id")
        field_name = str(payload.get("field_name", "")).strip()
        if card_id is None and note_id is None:
            raise ControlHTTPError(400, "target requires card_id or note_id.")
        if not field_name:
            raise ControlHTTPError(400, "target.field_name is required.")

        return cls(
            card_id=card_id,
            note_id=note_id,
            field_name=field_name,
            deck_name=str(payload.get("deck_name", "")).strip(),
            label=str(payload.get("label", "")).strip()[:160],
        )


@dataclass(frozen=True)
class VoiceOptions:
    review_before_save: bool = True
    dry_run: bool = False

    @classmethod
    def from_payload(cls, payload: object) -> "VoiceOptions":
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise ControlHTTPError(400, "options must be a JSON object.")
        return cls(
            review_before_save=bool(payload.get("review_before_save", True)),
            dry_run=bool(payload.get("dry_run", False)),
        )


@dataclass
class VoiceJob:
    job_id: str
    created_order: int
    target: TargetSnapshot
    options: VoiceOptions
    audio_path: Path | None = None
    transcript: str = ""
    state: str = "queued"
    error: str = ""

    def review_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "card_id": self.target.card_id,
            "note_id": self.target.note_id,
            "field_name": self.target.field_name,
            "deck_name": self.target.deck_name,
            "label": self.target.label,
            "transcript": self.transcript,
            "dry_run": self.options.dry_run,
            "state": self.state,
            "error": self.error,
        }


class AnkiGateway:
    def current_card(self) -> CurrentCard:
        return get_current_review_card()

    def resolve_note_id(self, card_id: int) -> int:
        return resolve_note_id_from_card(card_id)

    def note_fields(self, note_id: int) -> dict[str, str]:
        return get_note_fields(note_id)

    def selected_browser_note_ids(self) -> list[int]:
        return get_selected_browser_note_ids()

    def current_card_id(self) -> int | None:
        return get_current_review_card_id()

    def update_field(self, note_id: int, field_name: str, value: str) -> None:
        update_note_field(note_id, field_name, value)


class VoiceService:
    def __init__(
        self,
        *,
        recorder: Any | None = None,
        transcribe: Callable[[Path], str] | None = None,
        preload: Callable[[], None] | None = None,
        gateway: AnkiGateway | None = None,
        log: Callable[[str], None] | None = None,
        start_worker: bool = True,
        preload_in_background: bool = True,
    ) -> None:
        self.recorder = recorder if recorder is not None else _make_recorder()
        self.transcribe = transcribe or _transcribe_audio
        self.preload = preload or _preload_model
        self.gateway = gateway or AnkiGateway()
        self.log = log or _write_helper_log

        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._jobs: dict[str, VoiceJob] = {}
        self._job_queue: queue.Queue[str | None] = queue.Queue()
        self._recording_target: TargetSnapshot | None = None
        self._recording_options: VoiceOptions | None = None
        self._recording_job_id: str | None = None
        self._created_order = 0
        self._revision = 0
        self._event_id = 0
        self._events: deque[dict[str, Any]] = deque(maxlen=200)
        self._model_state = "loading" if preload_in_background else "not_loaded"
        self._model_error = ""
        self._shutdown = threading.Event()

        if start_worker:
            threading.Thread(target=self._worker_loop, daemon=True).start()
        if preload_in_background:
            threading.Thread(target=self._preload_worker, daemon=True).start()

        self.log("Anki Voice Field v2 headless service is ready.")

    def start_recording(
        self,
        target: TargetSnapshot,
        options: VoiceOptions,
        *,
        replacement_job_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.recorder.is_recording or self._recording_target is not None:
                raise ControlHTTPError(409, "A recording is already in progress.")
            self.recorder.start()
            self._recording_target = target
            self._recording_options = options
            self._recording_job_id = replacement_job_id
            self._touch()
            self._emit(
                "recording_started",
                f'Recording for "{target.field_name}".',
                card_id=target.card_id,
                note_id=target.note_id,
                field_name=target.field_name,
            )
        self.log(
            f"Recording started for card {target.card_id}, note {target.note_id}, "
            f'field "{target.field_name}".'
        )
        return {"message": "Recording...", "state": self.state()}

    def stop_recording(self) -> dict[str, Any]:
        with self._lock:
            if not self.recorder.is_recording or self._recording_target is None:
                raise ControlHTTPError(409, "No recording is in progress.")

            target = self._recording_target
            options = self._recording_options or VoiceOptions()
            replacement_job_id = self._recording_job_id
            try:
                audio_path = self.recorder.stop()
            finally:
                self._recording_target = None
                self._recording_options = None
                self._recording_job_id = None

            if replacement_job_id is not None:
                job = self._require_job(replacement_job_id)
                job.audio_path = audio_path
                job.transcript = ""
                job.error = ""
                job.state = "queued"
            else:
                self._created_order += 1
                job = VoiceJob(
                    job_id=uuid.uuid4().hex,
                    created_order=self._created_order,
                    target=target,
                    options=options,
                    audio_path=audio_path,
                )
                self._jobs[job.job_id] = job

            self._touch()
            self._emit(
                "recording_queued",
                "Recording queued for transcription.",
                job_id=job.job_id,
                field_name=job.target.field_name,
            )
            self._job_queue.put(job.job_id)

        self.log(f"Recording stopped and queued as job {job.job_id}.")
        return {
            "message": "Recording stopped. Transcribing...",
            "job_id": job.job_id,
            "state": self.state(),
        }

    def save_job(self, job_id: str, transcript: str) -> dict[str, Any]:
        corrected = transcript.strip()
        if not corrected:
            raise ControlHTTPError(400, "Transcript cannot be empty.")

        with self._lock:
            job = self._require_job(job_id)
            if job.state not in REVIEW_JOB_STATES:
                raise ControlHTTPError(409, "This job is not waiting for review.")
            job.transcript = corrected
            job.error = ""
            job.state = "saving"
            self._touch()

        threading.Thread(
            target=self._save_job,
            args=(job_id, corrected, False),
            daemon=True,
        ).start()
        return {"message": "Saving transcript...", "job_id": job_id}

    def rerecord_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._require_job(job_id)
            if job.state not in REVIEW_JOB_STATES:
                raise ControlHTTPError(409, "This job cannot be re-recorded now.")
            target = job.target
            options = job.options
            job.state = "rerecording"
            job.error = ""
            self._touch()

        try:
            return self.start_recording(
                target,
                options,
                replacement_job_id=job_id,
            )
        except Exception:
            with self._lock:
                job.state = "awaiting_review"
                self._touch()
            raise

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._require_job(job_id)
            if job.state in {"saving", "completed", "canceled"}:
                raise ControlHTTPError(409, "This job can no longer be canceled.")
            job.state = "canceled"
            job.error = ""
            self._touch()
            self._emit(
                "job_canceled",
                "Transcript canceled; Anki was not modified.",
                job_id=job_id,
            )
        self._delete_audio(job.audio_path)
        return {"message": "Transcript canceled.", "job_id": job_id}

    def state(self, after_event_id: int = 0) -> dict[str, Any]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.created_order)
            pending_reviews = [
                job.review_payload()
                for job in jobs
                if job.state in REVIEW_JOB_STATES and job.transcript
            ]
            events = [event.copy() for event in self._events if event["id"] > after_event_id]
            phase = self._derive_phase(jobs)
            current_target = (
                _target_payload(self._recording_target)
                if self._recording_target is not None
                else None
            )
            return {
                "protocol_version": PROTOCOL_VERSION,
                "revision": self._revision,
                "phase": phase,
                "status_message": self._status_message(phase, jobs),
                "model_state": self._model_state,
                "model_error": self._model_error,
                "recording": self.recorder.is_recording,
                "current_target": current_target,
                "queue_count": sum(job.state in ACTIVE_JOB_STATES for job in jobs),
                "pending_reviews": pending_reviews,
                "events": events,
                "next_event_id": self._event_id,
            }

    def handle_request(self, request: ControlRequest) -> dict[str, Any]:
        if request.path == "/health":
            return {
                "message": "Anki Voice Field v2 helper is running.",
                "protocol_version": PROTOCOL_VERSION,
            }

        if request.method == "GET" and request.path == "/v2/state":
            raw_after = request.query.get("after", ["0"])[0]
            try:
                after = max(0, int(raw_after))
            except ValueError as exc:
                raise ControlHTTPError(400, "after must be an integer.") from exc
            return self.state(after)

        if request.method == "POST" and request.path == "/v2/recordings/start":
            target = TargetSnapshot.from_payload(request.body.get("target"))
            options = VoiceOptions.from_payload(request.body.get("options"))
            return self.start_recording(target, options)

        if request.method == "POST" and request.path == "/v2/recordings/stop":
            return self.stop_recording()

        match = re.fullmatch(r"/v2/jobs/([0-9a-f]+)/(?P<action>save|rerecord|cancel)", request.path)
        if request.method == "POST" and match:
            job_id = match.group(1)
            action = match.group("action")
            if action == "save":
                return self.save_job(job_id, str(request.body.get("transcript", "")))
            if action == "rerecord":
                return self.rerecord_job(job_id)
            return self.cancel_job(job_id)

        if request.path == "/toggle":
            return self._legacy_toggle()
        if request.path == "/show":
            return {"message": "Open the legacy client from Anki's Tools menu."}
        if request.path == "/test-anki":
            return self._legacy_test_anki()

        raise ControlHTTPError(404, "Unknown command.")

    def process_next_job(self, timeout: float | None = None) -> bool:
        try:
            job_id = self._job_queue.get(timeout=timeout)
        except queue.Empty:
            return False
        if job_id is None:
            self._job_queue.task_done()
            return False
        try:
            self._process_voice_job(job_id)
        finally:
            self._job_queue.task_done()
        return True

    def close(self) -> None:
        self._shutdown.set()
        if self.recorder.is_recording:
            try:
                self.recorder.stop()
            except RuntimeError:
                pass
        self._job_queue.put(None)

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            self.process_next_job()

    def _preload_worker(self) -> None:
        try:
            self.preload()
        except Exception as exc:
            with self._lock:
                self._model_state = "error"
                self._model_error = str(exc)
                self._touch()
                self._emit("model_error", f"Speech model failed to load: {exc}")
            self.log(f"Speech model preload failed: {exc}")
        else:
            with self._lock:
                self._model_state = "ready"
                self._model_error = ""
                self._touch()
                self._emit("model_ready", "Speech model loaded.")
            self.log("Speech model loaded. Future notes should be faster.")

    def _process_voice_job(self, job_id: str) -> None:
        transcript = ""
        with self._lock:
            job = self._require_job(job_id)
            if job.state == "canceled":
                return
            job.state = "transcribing"
            job.error = ""
            audio_path = job.audio_path
            self._touch()

        if audio_path is None:
            self._fail_job(job_id, "Queued job has no audio file.")
            return

        try:
            if job.target.note_id is None:
                if job.target.card_id is None:
                    raise RuntimeError("Queued job has no locked card ID.")
                note_id = self.gateway.resolve_note_id(job.target.card_id)
                with self._lock:
                    job.target = TargetSnapshot(
                        card_id=job.target.card_id,
                        note_id=note_id,
                        field_name=job.target.field_name,
                        deck_name=job.target.deck_name,
                        label=job.target.label,
                    )

            transcript = self.transcribe(audio_path).strip()
            if not transcript:
                raise RuntimeError("No speech was transcribed from the recording.")

            with self._lock:
                job.transcript = transcript
                job.audio_path = None
                self._touch()
            self.log(f"Job {job_id} transcript: {transcript}")

            if job.options.review_before_save:
                with self._lock:
                    job.state = "awaiting_review"
                    self._touch()
                    self._emit(
                        "review_ready",
                        "Transcript is ready for review.",
                        job_id=job_id,
                        field_name=job.target.field_name,
                    )
                return

            self._save_job(job_id, transcript, True)
        except Exception as exc:
            self._fail_job(job_id, str(exc), transcript=transcript)
        finally:
            self._delete_audio(audio_path)

    def _save_job(self, job_id: str, transcript: str, automatic: bool) -> None:
        with self._lock:
            job = self._require_job(job_id)
            job.state = "saving"
            job.error = ""
            target = job.target
            options = job.options
            self._touch()

        try:
            note_id = target.note_id
            if note_id is None:
                if target.card_id is None:
                    raise AnkiConnectError("Voice job has no target note or card ID.")
                note_id = self.gateway.resolve_note_id(target.card_id)

            fields = self.gateway.note_fields(note_id)
            if target.field_name not in fields:
                raise MissingFieldError(target.field_name, list(fields.keys()))

            existing_value = fields[target.field_name]
            timestamp = datetime.now()
            updated_value = append_transcript_to_field(
                existing_value,
                transcript,
                timestamp,
            )
            appended_count = len(updated_value) - len(existing_value)

            if options.dry_run:
                with self._lock:
                    job.state = "completed"
                    self._touch()
                    self._emit(
                        "dry_run_complete",
                        f"Dry run complete; {appended_count} characters previewed.",
                        job_id=job_id,
                        transcript=transcript,
                    )
                return

            wait_seconds = (
                config.FAST_MODE_WAIT_FOR_CARD_CHANGE_SECONDS
                if automatic
                else config.WAIT_FOR_TARGET_CARD_CHANGE_SECONDS
            )
            self._write_and_verify(
                note_id,
                target.card_id,
                target.field_name,
                updated_value,
                transcript,
                timestamp,
                wait_for_card_change_seconds=wait_seconds,
            )
            append_saved_voice_note(
                saved_at=datetime.now(),
                card_id=target.card_id,
                note_id=note_id,
                field_name=target.field_name,
                transcript=transcript,
            )

            with self._lock:
                job.state = "completed"
                job.error = ""
                self._touch()
                self._emit(
                    "saved",
                    f'Appended {appended_count} characters to "{target.field_name}".',
                    job_id=job_id,
                    field_name=target.field_name,
                    transcript=transcript,
                )
            self.log(
                f"Updated note {note_id}. Verified append of {appended_count} "
                f'characters to "{target.field_name}".'
            )
        except Exception as exc:
            self._fail_job(job_id, str(exc), transcript=transcript)

    def _write_and_verify(
        self,
        note_id: int,
        card_id: int | None,
        field_name: str,
        updated_value: str,
        transcript: str,
        timestamp: datetime,
        *,
        wait_for_card_change_seconds: float | None,
    ) -> None:
        with self._write_lock:
            if note_id in self.gateway.selected_browser_note_ids():
                raise UpdateVerificationError(
                    "This note is selected in Anki Browser. Close Browser or select "
                    "a different note, then retry Save To Anki."
                )

            if self._field_requires_card_change_before_save(field_name):
                self._wait_until_target_card_is_not_current(
                    card_id,
                    wait_for_card_change_seconds,
                )

            for attempt in range(1, config.SAVE_RETRY_ATTEMPTS + 1):
                self.log(
                    f"Save attempt {attempt}/{config.SAVE_RETRY_ATTEMPTS} "
                    f"for note {note_id}."
                )
                self.gateway.update_field(note_id, field_name, updated_value)
                if self._wait_for_verified_append(
                    note_id,
                    field_name,
                    transcript,
                    timestamp,
                ):
                    return

        raise UpdateVerificationError(
            "Anki accepted the write request, but the field did not stay changed. "
            "Close Anki Browser/editor if it is open, then retry Save To Anki."
        )

    def _wait_until_target_card_is_not_current(
        self,
        card_id: int | None,
        wait_seconds: float | None,
    ) -> None:
        if card_id is None:
            return
        deadline = None if wait_seconds is None else time.monotonic() + wait_seconds
        while deadline is None or time.monotonic() <= deadline:
            try:
                current_card_id = self.gateway.current_card_id()
            except AnkiConnectError:
                return
            if current_card_id != card_id:
                return
            time.sleep(config.WAIT_FOR_TARGET_CARD_CHANGE_POLL_SECONDS)
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
            value = self.gateway.note_fields(note_id).get(field_name, "")
            if field_contains_appended_transcript(value, transcript, timestamp):
                time.sleep(config.POST_SAVE_STABLE_SECONDS)
                stable_value = self.gateway.note_fields(note_id).get(field_name, "")
                return field_contains_appended_transcript(
                    stable_value,
                    transcript,
                    timestamp,
                )
            time.sleep(config.POST_SAVE_VERIFY_POLL_SECONDS)
        return False

    @staticmethod
    def _field_requires_card_change_before_save(field_name: str) -> bool:
        required = {
            configured.casefold()
            for configured in config.FIELDS_THAT_REQUIRE_CARD_CHANGE_BEFORE_SAVE
        }
        return field_name.casefold() in required

    def _legacy_toggle(self) -> dict[str, Any]:
        if self.recorder.is_recording:
            return self.stop_recording()
        try:
            card = self.gateway.current_card()
            field_name = choose_target_field(card.fields, card.model_name)
            note_id = self.gateway.resolve_note_id(card.card_id)
        except (AnkiConnectError, MissingFieldError) as exc:
            raise ControlHTTPError(409, str(exc)) from exc
        return self.start_recording(
            TargetSnapshot(
                card_id=card.card_id,
                note_id=note_id,
                field_name=field_name,
                deck_name=card.deck_name,
            ),
            VoiceOptions(
                review_before_save=config.REVIEW_TRANSCRIPT_BEFORE_WRITE_DEFAULT,
                dry_run=config.DRY_RUN_DEFAULT,
            ),
        )

    def _legacy_test_anki(self) -> dict[str, Any]:
        try:
            card = self.gateway.current_card()
            field_name = choose_target_field(card.fields, card.model_name)
        except (AnkiConnectError, MissingFieldError) as exc:
            raise ControlHTTPError(409, str(exc)) from exc
        return {
            "message": f'Connected. Current card will use "{field_name}".',
            "card_id": card.card_id,
            "deck_name": card.deck_name,
            "model_name": card.model_name,
            "field_name": field_name,
        }

    def _fail_job(self, job_id: str, message: str, *, transcript: str = "") -> None:
        with self._lock:
            job = self._require_job(job_id)
            if transcript:
                job.transcript = transcript
            job.state = "error"
            job.error = message
            self._touch()
            self._emit(
                "error",
                message,
                job_id=job_id,
                field_name=job.target.field_name,
                recoverable=bool(job.transcript),
            )
        self.log(f"Job {job_id} error: {message}")

    def _derive_phase(self, jobs: list[VoiceJob]) -> str:
        if self.recorder.is_recording:
            return "recording"
        for phase in ("transcribing", "saving", "awaiting_review", "queued", "error"):
            if any(job.state == phase for job in jobs):
                return "waiting_review" if phase == "awaiting_review" else phase
        return "ready"

    def _status_message(self, phase: str, jobs: list[VoiceJob]) -> str:
        messages = {
            "recording": "Recording... press F8 again to stop.",
            "transcribing": "Transcribing voice note...",
            "saving": "Saving and verifying in Anki...",
            "waiting_review": "Transcript ready for review.",
            "queued": "Voice note queued.",
            "error": "Voice note needs attention.",
            "ready": "Ready. Press F8 to record.",
        }
        if phase == "ready" and self._model_state == "loading":
            return "Ready. Speech model is loading in the background."
        return messages[phase]

    def _require_job(self, job_id: str) -> VoiceJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise ControlHTTPError(404, "Voice job was not found.") from exc

    def _touch(self) -> None:
        self._revision += 1

    def _emit(self, event_type: str, message: str, **details: Any) -> None:
        self._event_id += 1
        self._events.append(
            {
                "id": self._event_id,
                "type": event_type,
                "message": message,
                **details,
            }
        )
        self._touch()

    @staticmethod
    def _delete_audio(audio_path: Path | None) -> None:
        if audio_path is None:
            return
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass


def _optional_int(value: object, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ControlHTTPError(400, f"{name} must be an integer.") from exc


def _target_payload(target: TargetSnapshot) -> dict[str, Any]:
    return {
        "card_id": target.card_id,
        "note_id": target.note_id,
        "field_name": target.field_name,
        "deck_name": target.deck_name,
        "label": target.label,
    }
