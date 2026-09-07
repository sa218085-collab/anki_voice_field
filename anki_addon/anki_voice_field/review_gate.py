from __future__ import annotations

from typing import Any


class ReviewGate:
    """Select one FIFO review job without opening duplicate dialogs."""

    def __init__(self) -> None:
        self.active_job_id: str | None = None
        self.handled_job_ids: set[str] = set()

    def next_job(self, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
        present_ids = {str(job.get("job_id", "")) for job in jobs}
        self.handled_job_ids.intersection_update(present_ids)
        if self.active_job_id is not None:
            return None
        for job in jobs:
            job_id = str(job.get("job_id", ""))
            if job_id and job_id not in self.handled_job_ids:
                self.active_job_id = job_id
                return job
        return None

    def mark_handled(self, job_id: str) -> None:
        self.handled_job_ids.add(job_id)

    def dialog_closed(self, job_id: str) -> None:
        if self.active_job_id == job_id:
            self.active_job_id = None
