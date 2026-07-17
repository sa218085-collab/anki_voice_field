from __future__ import annotations

import sys
import unittest
from concurrent.futures import Future
from pathlib import Path


ADDON_FOLDER = Path(__file__).resolve().parents[1] / "anki_addon" / "anki_voice_field"
sys.path.insert(0, str(ADDON_FOLDER))

from async_runner import BackgroundRunner  # noqa: E402
from review_gate import ReviewGate  # noqa: E402


class FakeTaskManager:
    def __init__(self) -> None:
        self.calls = []

    def run_in_background(self, task, on_done, *, uses_collection):  # type: ignore[no-untyped-def]
        self.calls.append((task, on_done, uses_collection))
        return Future()


class NativeUICoordinationTests(unittest.TestCase):
    def test_helper_calls_use_non_collection_background_executor(self) -> None:
        taskman = FakeTaskManager()
        runner = BackgroundRunner(taskman)
        network_was_called = False

        def network_call() -> None:
            nonlocal network_was_called
            network_was_called = True

        runner.submit(network_call, lambda _future: None)
        self.assertFalse(network_was_called)
        self.assertEqual(len(taskman.calls), 1)
        self.assertFalse(taskman.calls[0][2])

    def test_review_gate_opens_one_fifo_dialog_without_duplicates(self) -> None:
        gate = ReviewGate()
        jobs = [{"job_id": "first"}, {"job_id": "second"}]
        self.assertEqual(gate.next_job(jobs), jobs[0])
        self.assertIsNone(gate.next_job(jobs))

        gate.mark_handled("first")
        gate.dialog_closed("first")
        self.assertEqual(gate.next_job(jobs), jobs[1])
        gate.mark_handled("second")
        gate.dialog_closed("second")
        self.assertIsNone(gate.next_job(jobs))

        gate.next_job([])
        self.assertEqual(gate.handled_job_ids, set())


if __name__ == "__main__":
    unittest.main()
