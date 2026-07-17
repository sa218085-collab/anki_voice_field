from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class ServiceClientError(RuntimeError):
    pass


class ServiceClient:
    def __init__(self, base_url: str, *, timeout: float = 0.8) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return self._request("/health", method="GET")

    def state(self, after_event_id: int) -> dict[str, Any]:
        return self._request(f"/v2/state?after={after_event_id}", method="GET")

    def start_recording(
        self,
        target: dict[str, Any],
        *,
        review_before_save: bool,
        dry_run: bool,
    ) -> dict[str, Any]:
        return self._request(
            "/v2/recordings/start",
            body={
                "target": target,
                "options": {
                    "review_before_save": review_before_save,
                    "dry_run": dry_run,
                },
            },
        )

    def stop_recording(self) -> dict[str, Any]:
        return self._request("/v2/recordings/stop", body={})

    def save_job(self, job_id: str, transcript: str) -> dict[str, Any]:
        return self._request(
            f"/v2/jobs/{job_id}/save",
            body={"transcript": transcript},
        )

    def rerecord_job(self, job_id: str) -> dict[str, Any]:
        return self._request(f"/v2/jobs/{job_id}/rerecord", body={})

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._request(f"/v2/jobs/{job_id}/cancel", body={})

    def test_anki(self) -> dict[str, Any]:
        return self._request("/test-anki", body={})

    def _request(
        self,
        path: str,
        *,
        method: str = "POST",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = str(payload.get("error", exc.reason))
            except (UnicodeDecodeError, json.JSONDecodeError):
                message = str(exc.reason)
            raise ServiceClientError(message) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ServiceClientError(str(exc)) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceClientError("Helper returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise ServiceClientError("Helper returned an invalid response.")
        if not payload.get("ok", False):
            raise ServiceClientError(str(payload.get("error", "Unknown helper error.")))
        return dict(payload)
