from __future__ import annotations

import json
import tkinter as tk
import urllib.error
import urllib.request
from tkinter.scrolledtext import ScrolledText
from typing import Any

import config


def service_request(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = (
        f"http://{config.CONTROL_SERVER_HOST}:"
        f"{config.CONTROL_SERVER_PORT}{path}"
    )
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=1.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok", False):
        raise RuntimeError(str(payload.get("error", "Unknown helper error.")))
    return dict(payload)


class LegacyClient:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Anki Voice Field — Legacy Client")
        self.root.geometry("680x360")
        self.status = tk.StringVar(value="Connecting to the v2 helper...")
        self.event_cursor = 0
        self.active_review_job_id: str | None = None

        frame = tk.Frame(root, padx=14, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(frame, textvariable=self.status, font=("Segoe UI", 11, "bold")).pack(
            anchor="w"
        )
        controls = tk.Frame(frame)
        controls.pack(fill=tk.X, pady=(10, 8))
        tk.Button(controls, text="Record / Stop", width=18, command=self.toggle).pack(
            side=tk.LEFT
        )
        tk.Button(controls, text="Test Anki", width=14, command=self.test_anki).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self.log_box = ScrolledText(frame, height=14, wrap=tk.WORD)
        self.log_box.pack(fill=tk.BOTH, expand=True)
        self.log_box.configure(state=tk.DISABLED)
        self.poll()

    def log(self, message: str) -> None:
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"{message}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def toggle(self) -> None:
        try:
            payload = service_request("/toggle", {})
        except Exception as exc:
            self.log(f"Record command failed: {exc}")
        else:
            self.status.set(str(payload.get("message", "Voice note toggled.")))

    def test_anki(self) -> None:
        try:
            payload = service_request("/test-anki", {})
        except Exception as exc:
            self.log(f"Anki test failed: {exc}")
        else:
            self.log(str(payload.get("message", "Anki connection succeeded.")))

    def poll(self) -> None:
        try:
            state = service_request(f"/v2/state?after={self.event_cursor}")
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            self.status.set("Helper unavailable. Start it from Anki.")
            self.log_once(f"Helper unavailable: {exc}")
        else:
            self.status.set(str(state.get("status_message", "Ready.")))
            for event in state.get("events", []):
                self.log(str(event.get("message", "")))
            self.event_cursor = int(state.get("next_event_id", self.event_cursor))
            reviews = state.get("pending_reviews", [])
            if reviews and self.active_review_job_id is None:
                self.show_review(dict(reviews[0]))
        self.root.after(500, self.poll)

    def log_once(self, message: str) -> None:
        current = self.log_box.get("end-2l", "end-1c")
        if current != message:
            self.log(message)

    def show_review(self, job: dict[str, Any]) -> None:
        job_id = str(job["job_id"])
        self.active_review_job_id = job_id
        popup = tk.Toplevel(self.root)
        popup.title("Review Voice Note")
        popup.geometry("620x350+90+90")

        frame = tk.Frame(popup, padx=12, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)
        field_name = str(job.get("field_name", "unknown"))
        tk.Label(
            frame,
            text=f'Review before appending to "{field_name}"',
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        if job.get("error"):
            tk.Label(frame, text=str(job["error"]), fg="#b3261e", wraplength=570).pack(
                anchor="w", pady=(4, 0)
            )
        text_box = ScrolledText(frame, height=11, wrap=tk.WORD)
        text_box.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
        text_box.insert(tk.END, str(job.get("transcript", "")))
        text_box.focus_set()

        buttons = tk.Frame(frame)
        buttons.pack(fill=tk.X)

        def finish() -> None:
            self.active_review_job_id = None
            popup.destroy()

        def save() -> None:
            transcript = text_box.get("1.0", tk.END).strip()
            try:
                service_request(
                    f"/v2/jobs/{job_id}/save",
                    {"transcript": transcript},
                )
            except Exception as exc:
                self.log(f"Save failed: {exc}")
                return
            finish()

        def rerecord() -> None:
            try:
                service_request(f"/v2/jobs/{job_id}/rerecord", {})
            except Exception as exc:
                self.log(f"Re-record failed: {exc}")
                return
            finish()

        def cancel() -> None:
            try:
                service_request(f"/v2/jobs/{job_id}/cancel", {})
            except Exception as exc:
                self.log(f"Cancel failed: {exc}")
                return
            finish()

        tk.Button(buttons, text="Save To Anki", width=16, command=save).pack(side=tk.LEFT)
        tk.Button(buttons, text="Re-record", width=14, command=rerecord).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        tk.Button(buttons, text="Cancel", width=12, command=cancel).pack(side=tk.RIGHT)
        popup.bind("<Control-Return>", lambda _event: save())
        popup.protocol("WM_DELETE_WINDOW", cancel)


def main() -> None:
    root = tk.Tk()
    LegacyClient(root)
    root.mainloop()


if __name__ == "__main__":
    main()
