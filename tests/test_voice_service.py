from __future__ import annotations

import time
import unittest

import config
from anki_client import CurrentCard
from control_server import ControlHTTPError, ControlRequest
from voice_service import TargetSnapshot, VoiceOptions, VoiceService


class DummyAudio:
    def __init__(self, name: str) -> None:
        self.name = name
        self.deleted = False

    def unlink(self, *, missing_ok: bool = False) -> None:
        self.deleted = True


class FakeRecorder:
    def __init__(self) -> None:
        self.is_recording = False
        self.counter = 0

    def start(self) -> None:
        if self.is_recording:
            raise RuntimeError("already recording")
        self.is_recording = True

    def stop(self) -> DummyAudio:
        if not self.is_recording:
            raise RuntimeError("not recording")
        self.is_recording = False
        self.counter += 1
        return DummyAudio(f"audio-{self.counter}.wav")


class FakeGateway:
    def __init__(self) -> None:
        self.fields: dict[int, dict[str, str]] = {
            101: {"Front": "Question one", "Lecture Notes": ""},
            202: {"Front": "Question two", "Lecture Notes": ""},
        }
        self.current_id: int | None = None
        self.fail_update = False

    def current_card(self) -> CurrentCard:
        return CurrentCard(
            card_id=1,
            deck_name="Test",
            model_name="Basic",
            fields=self.fields[101].copy(),
        )

    def resolve_note_id(self, card_id: int) -> int:
        return {1: 101, 2: 202}[card_id]

    def note_fields(self, note_id: int) -> dict[str, str]:
        return self.fields[note_id].copy()

    def selected_browser_note_ids(self) -> list[int]:
        return []

    def current_card_id(self) -> int | None:
        return self.current_id

    def update_field(self, note_id: int, field_name: str, value: str) -> None:
        if self.fail_update:
            raise RuntimeError("simulated write failure")
        self.fields[note_id][field_name] = value


class VoiceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = FakeGateway()
        self.transcripts = ["first transcript", "second transcript", "third transcript"]
        self.original_timing = {
            "POST_SAVE_STABLE_SECONDS": config.POST_SAVE_STABLE_SECONDS,
            "POST_SAVE_VERIFY_TIMEOUT_SECONDS": config.POST_SAVE_VERIFY_TIMEOUT_SECONDS,
            "POST_SAVE_VERIFY_POLL_SECONDS": config.POST_SAVE_VERIFY_POLL_SECONDS,
            "WAIT_FOR_TARGET_CARD_CHANGE_POLL_SECONDS": config.WAIT_FOR_TARGET_CARD_CHANGE_POLL_SECONDS,
            "SAVE_RETRY_ATTEMPTS": config.SAVE_RETRY_ATTEMPTS,
        }
        config.POST_SAVE_STABLE_SECONDS = 0
        config.POST_SAVE_VERIFY_TIMEOUT_SECONDS = 0.1
        config.POST_SAVE_VERIFY_POLL_SECONDS = 0.001
        config.WAIT_FOR_TARGET_CARD_CHANGE_POLL_SECONDS = 0.001
        config.SAVE_RETRY_ATTEMPTS = 1
        self.service = VoiceService(
            recorder=FakeRecorder(),
            transcribe=lambda _path: self.transcripts.pop(0),
            gateway=self.gateway,  # type: ignore[arg-type]
            log=lambda _message: None,
            start_worker=False,
            preload_in_background=False,
        )

    def tearDown(self) -> None:
        self.service.close()
        for name, value in self.original_timing.items():
            setattr(config, name, value)

    def target(self, card_id: int = 1, note_id: int = 101) -> TargetSnapshot:
        return TargetSnapshot(
            card_id=card_id,
            note_id=note_id,
            field_name="Lecture Notes",
            deck_name="Test",
            label=f"Card {card_id}",
        )

    def record_once(self, target: TargetSnapshot, options: VoiceOptions | None = None) -> str:
        self.service.start_recording(target, options or VoiceOptions())
        result = self.service.stop_recording()
        return str(result["job_id"])

    def wait_for_event(self, event_type: str) -> dict:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            for event in self.service.state()["events"]:
                if event["type"] == event_type:
                    return event
            time.sleep(0.005)
        self.fail(f"Timed out waiting for {event_type}")

    def test_target_is_locked_and_reviewed_before_save(self) -> None:
        job_id = self.record_once(self.target())
        self.gateway.current_id = 2
        self.assertTrue(self.service.process_next_job(timeout=0.1))

        review = self.service.state()["pending_reviews"][0]
        self.assertEqual(review["job_id"], job_id)
        self.assertEqual(review["card_id"], 1)
        self.assertEqual(review["note_id"], 101)
        self.assertEqual(review["field_name"], "Lecture Notes")

        self.service.save_job(job_id, "corrected transcript")
        self.wait_for_event("saved")
        self.assertIn("corrected transcript", self.gateway.fields[101]["Lecture Notes"])
        self.assertEqual(self.gateway.fields[202]["Lecture Notes"], "")

    def test_fifo_reviews_and_event_cursor(self) -> None:
        first_id = self.record_once(self.target(1, 101))
        second_id = self.record_once(self.target(2, 202))
        self.service.process_next_job(timeout=0.1)
        self.service.process_next_job(timeout=0.1)

        state = self.service.state()
        self.assertEqual(
            [job["job_id"] for job in state["pending_reviews"]],
            [first_id, second_id],
        )
        cursor = state["next_event_id"]
        self.assertEqual(self.service.state(cursor)["events"], [])

    def test_rerecord_reuses_locked_target_then_cancel(self) -> None:
        job_id = self.record_once(self.target())
        self.service.process_next_job(timeout=0.1)
        self.service.rerecord_job(job_id)
        stopped = self.service.stop_recording()
        self.assertEqual(stopped["job_id"], job_id)
        self.service.process_next_job(timeout=0.1)

        review = self.service.state()["pending_reviews"][0]
        self.assertEqual(review["transcript"], "second transcript")
        self.service.cancel_job(job_id)
        state = self.service.state()
        self.assertEqual(state["pending_reviews"], [])
        self.assertEqual(state["queue_count"], 0)

    def test_failed_automatic_save_is_recoverable(self) -> None:
        self.gateway.fail_update = True
        job_id = self.record_once(
            self.target(),
            VoiceOptions(review_before_save=False),
        )
        self.service.process_next_job(timeout=0.1)

        review = self.service.state()["pending_reviews"][0]
        self.assertEqual(review["job_id"], job_id)
        self.assertIn("simulated write failure", review["error"])
        self.assertEqual(review["transcript"], "first transcript")

        self.gateway.fail_update = False
        self.service.save_job(job_id, review["transcript"])
        self.wait_for_event("saved")
        self.assertIn("first transcript", self.gateway.fields[101]["Lecture Notes"])

    def test_api_validation_and_unknown_routes(self) -> None:
        with self.assertRaises(ControlHTTPError):
            TargetSnapshot.from_payload({"field_name": "Lecture Notes"})
        with self.assertRaises(ControlHTTPError):
            self.service.handle_request(
                ControlRequest("GET", "/v2/state", {"after": ["bad"]}, {})
            )
        with self.assertRaises(ControlHTTPError):
            self.service.handle_request(ControlRequest("POST", "/unknown", {}, {}))


if __name__ == "__main__":
    unittest.main()
