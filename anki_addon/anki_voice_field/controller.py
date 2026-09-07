from __future__ import annotations

import html
import json
import re
import subprocess
import time
from collections import deque
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

from aqt import gui_hooks, mw
from aqt.qt import QKeySequence, QShortcut, QTimer, Qt
from aqt.reviewer import ReviewerBottomBar
from aqt.utils import qconnect, showInfo, tooltip

from .async_runner import BackgroundRunner
from .review_dialog import ReviewDialog
from .review_gate import ReviewGate
from .service_client import ServiceClient, ServiceClientError
from .settings_dialog import VoiceSettingsDialog


ADDON_MODULE = __package__ or __name__
PROTOCOL_VERSION = 2
DEFAULT_CONFIG: dict[str, Any] = {
    "helper_project_folder": "__BUNDLED__",
    "helper_pythonw_path": "__AUTO__",
    "control_url": "http://127.0.0.1:47866",
    "auto_start_helper": True,
    "auto_launch_helper_on_anki_startup": True,
    "auto_setup_helper": False,
    "target_field_name": "Lecture Notes",
    "image_occlusion_model_hints": ["Image Occlusion"],
    "image_occlusion_fallback_field_name": "Remarks",
    "default_fallback_field_names": ["Back", "Extra", "Back Extra", "Remarks"],
    "hotkey": "F8",
    "review_before_save": True,
    "dry_run": False,
    "poll_interval_ms": 250,
}


class NativeVoiceController:
    def __init__(self) -> None:
        self.client = ServiceClient(str(self.config()["control_url"]))
        self.background = BackgroundRunner(mw.taskman)
        self.review_gate = ReviewGate()
        self.current_target: dict[str, Any] | None = None
        self.target_error = "Start reviewing a card first."
        self.helper_state: dict[str, Any] = {
            "phase": "starting",
            "status_message": "Starting voice helper...",
            "queue_count": 0,
            "recording": False,
            "pending_reviews": [],
            "events": [],
            "model_state": "loading",
        }
        self.event_cursor = 0
        self.last_revision = -1
        self.last_connection_error = ""
        self.protocol_mismatch = False
        self.setup_required = False
        self.poll_in_flight = False
        self.command_in_flight = False
        self.last_start_attempt = 0.0
        self.active_dialog: ReviewDialog | None = None
        self.settings_dialog: VoiceSettingsDialog | None = None
        self.recent_activity: deque[str] = deque(maxlen=150)
        self.shortcuts: list[QShortcut] = []

        self.poll_timer = QTimer(mw)
        self.poll_timer.setInterval(max(100, int(self.config()["poll_interval_ms"])))
        qconnect(self.poll_timer.timeout, self.poll_state)
        self.poll_timer.start()

        self._setup_web_assets()
        self._setup_hooks()
        self._setup_config_action()
        self._setup_hotkey()
        self._add_activity("Anki Voice Field v2 loaded inside Anki.")
        if bool(self.config()["auto_launch_helper_on_anki_startup"]):
            QTimer.singleShot(1200, self.ensure_helper_started)

    def config(self) -> dict[str, Any]:
        stored = mw.addonManager.getConfig(ADDON_MODULE)
        merged = DEFAULT_CONFIG.copy()
        if isinstance(stored, dict):
            merged.update(stored)
        return merged

    def addon_folder(self) -> Path:
        return Path(__file__).resolve().parent

    def helper_folder(self) -> Path:
        raw = str(self.config()["helper_project_folder"]).strip()
        if not raw or raw == "__BUNDLED__":
            return self.addon_folder() / "helper"
        return Path(raw)

    def helper_pythonw(self) -> Path:
        project = self.helper_folder()
        raw = str(self.config()["helper_pythonw_path"]).strip()
        if not raw or raw == "__AUTO__":
            return project / ".venv" / "Scripts" / "pythonw.exe"
        return Path(raw)

    def ensure_helper_started(self) -> None:
        if not bool(self.config()["auto_start_helper"]):
            return
        now = time.monotonic()
        if now - self.last_start_attempt < 8.0:
            return
        self.last_start_attempt = now

        project = self.helper_folder()
        pythonw = self.helper_pythonw()
        entrypoint = project / "headless.pyw"
        if not project.exists() or not entrypoint.exists():
            self.setup_required = True
            self._set_offline("Bundled voice helper files are missing.")
            return
        if not pythonw.exists():
            self.setup_required = True
            self._set_offline("Voice helper setup is required.")
            if bool(self.config()["auto_setup_helper"]):
                self.launch_setup()
            return

        self.setup_required = False
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(
                [str(pythonw), str(entrypoint)],
                cwd=str(project),
                creationflags=creationflags,
            )
        except OSError as exc:
            self._set_offline(f"Could not start voice helper: {exc}")
            return
        self.helper_state.update(
            phase="starting",
            status_message="Starting voice helper...",
        )
        self.push_ui_state()

    def poll_state(self) -> None:
        if self.poll_in_flight:
            return
        self.poll_in_flight = True

        def done(future: Future) -> None:
            self.poll_in_flight = False
            try:
                state = dict(future.result())
            except Exception as exc:
                self.last_connection_error = str(exc)
                self._set_offline("Voice helper is offline.")
                self.ensure_helper_started()
                return

            if state.get("_protocol_mismatch"):
                self.protocol_mismatch = True
                self.last_connection_error = str(state["_protocol_mismatch"])
                self._set_offline("An older voice helper is still running.")
                return

            protocol = int(state.get("protocol_version", 0))
            if protocol != PROTOCOL_VERSION:
                self.protocol_mismatch = True
                self.last_connection_error = (
                    f"Expected helper protocol {PROTOCOL_VERSION}, received {protocol}."
                )
                self._set_offline("Voice helper must be restarted after the v2 update.")
                return

            self.last_connection_error = ""
            self.protocol_mismatch = False
            self.setup_required = False
            revision = int(state.get("revision", -1))
            self.helper_state = state
            self.event_cursor = int(state.get("next_event_id", self.event_cursor))
            self._process_events(list(state.get("events", [])))
            self._sync_review_dialogs(list(state.get("pending_reviews", [])))
            if revision != self.last_revision:
                self.last_revision = revision
                self.push_ui_state()

        def fetch_state() -> dict[str, Any]:
            try:
                return self.client.state(self.event_cursor)
            except ServiceClientError as state_error:
                try:
                    health = self.client.health()
                except ServiceClientError:
                    raise state_error
                protocol = int(health.get("protocol_version", 0))
                if protocol != PROTOCOL_VERSION:
                    return {
                        "_protocol_mismatch": (
                            "The running helper uses the v1 protocol. Close its old "
                            "status window or end its pythonw.exe process, then click Retry."
                        )
                    }
                raise state_error

        self.background.submit(
            fetch_state,
            done,
        )

    def toggle_recording(self) -> None:
        if self.command_in_flight:
            return
        if bool(self.helper_state.get("recording")):
            self._run_command(self.client.stop_recording)
            return
        if self.helper_state.get("phase") in {"offline", "starting"}:
            self.ensure_helper_started()
            tooltip("Starting Anki Voice Field helper...")
            return
        if self.current_target is None:
            tooltip(self.target_error)
            return

        settings = self.config()
        target = dict(self.current_target)
        self._run_command(
            lambda: self.client.start_recording(
                target,
                review_before_save=bool(settings["review_before_save"]),
                dry_run=bool(settings["dry_run"]),
            )
        )

    def set_review_before_save(self, enabled: bool) -> None:
        config = self.config()
        config["review_before_save"] = bool(enabled)
        mw.addonManager.writeConfig(ADDON_MODULE, config)
        self.push_ui_state()

    def save_settings(self, updates: dict[str, Any]) -> None:
        config = self.config()
        config.update(updates)
        config["poll_interval_ms"] = max(100, int(config["poll_interval_ms"]))
        mw.addonManager.writeConfig(ADDON_MODULE, config)

        self.client = ServiceClient(str(config["control_url"]))
        self.poll_timer.setInterval(int(config["poll_interval_ms"]))
        self._rebuild_hotkey()
        self._add_activity("Settings saved in Anki.")
        tooltip("Anki Voice Field settings saved.")
        self.push_ui_state()

    def test_connection(self) -> None:
        if self.helper_state.get("phase") in {"offline", "starting"}:
            self.ensure_helper_started()
            QTimer.singleShot(
                1200,
                lambda: self._run_command(self.client.test_anki),
            )
            return
        self._run_command(self.client.test_anki)

    def open_settings(self) -> None:
        if self.settings_dialog is not None:
            self.settings_dialog.showNormal()
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            self._refresh_settings_dialog()
            return

        dialog = VoiceSettingsDialog(
            mw,
            self.config(),
            save_settings=self.save_settings,
            toggle_recording=self.toggle_recording,
            test_connection=self.test_connection,
            retry_helper=self.ensure_helper_started,
            show_details=self.show_details,
            open_legacy_client=self.open_legacy_client,
        )
        self.settings_dialog = dialog

        def finished(_result: int) -> None:
            self.settings_dialog = None

        qconnect(dialog.finished, finished)
        self._refresh_settings_dialog()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def launch_setup(self) -> None:
        script = self.helper_folder() / "setup_helper_env.ps1"
        if not script.exists():
            showInfo(f"Helper setup script was not found:\n\n{script}")
            return
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=str(self.helper_folder()),
            )
        except OSError as exc:
            showInfo(f"Could not start helper setup:\n\n{exc}")
            return
        showInfo(
            "Helper setup has opened in PowerShell. When it finishes, restart "
            "Anki or click Retry in the voice strip."
        )

    def open_legacy_client(self) -> None:
        self.ensure_helper_started()
        pythonw = self.helper_pythonw()
        client_path = self.helper_folder() / "legacy_client.pyw"
        if not pythonw.exists() or not client_path.exists():
            showInfo("The helper environment or legacy client is not available yet.")
            return
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            [str(pythonw), str(client_path)],
            cwd=str(self.helper_folder()),
            creationflags=creationflags,
        )

    def show_details(self) -> None:
        parts = [
            f"State: {self.helper_state.get('phase', 'unknown')}",
            f"Status: {self.helper_state.get('status_message', '')}",
            f"Model: {self.helper_state.get('model_state', 'unknown')}",
            f"Queue: {self.helper_state.get('queue_count', 0)}",
            f"Helper: {self.helper_folder()}",
        ]
        error = self.last_connection_error or str(self.helper_state.get("model_error", ""))
        if error:
            parts.append(f"Error: {error}")
        if self.protocol_mismatch:
            parts.append(
                "Close the old Anki Voice Field status window (or its pythonw.exe "
                "process), then click Retry. The v2 helper cannot start while v1 "
                "still owns the local control port."
            )
        showInfo("\n\n".join(parts), title="Anki Voice Field")

    def push_ui_state(self) -> None:
        self._refresh_settings_dialog()
        reviewer = getattr(mw, "reviewer", None)
        bottom = getattr(reviewer, "bottom", None)
        web = getattr(bottom, "web", None)
        if web is None:
            return

        phase = str(self.helper_state.get("phase", "offline"))
        recording = bool(self.helper_state.get("recording", False))
        helper_target = self.helper_state.get("current_target")
        target = helper_target if recording and isinstance(helper_target, dict) else self.current_target
        field_name = str(target.get("field_name", "")) if isinstance(target, dict) else ""
        disabled = self.command_in_flight or (
            not recording
            and (phase in {"offline", "starting"} or self.current_target is None)
        )
        action_label = ""
        if self.setup_required:
            action_label = "Set up"
        elif self.protocol_mismatch:
            action_label = "Details"
        elif phase == "offline":
            action_label = "Retry"
        elif phase == "error" or self.helper_state.get("model_state") == "error":
            action_label = "Details"

        payload = {
            "phase": phase,
            "status": str(self.helper_state.get("status_message", "Voice helper is offline.")),
            "recording": recording,
            "button_label": "Stop" if recording else "Record",
            "button_disabled": disabled,
            "field": field_name or self.target_error,
            "field_available": bool(field_name),
            "queue_count": int(self.helper_state.get("queue_count", 0)),
            "review_before_save": bool(self.config()["review_before_save"]),
            "action_label": action_label,
        }
        web.eval(f"window.avfSetState && window.avfSetState({json.dumps(payload)});")

    def _setup_web_assets(self) -> None:
        mw.addonManager.setWebExports(ADDON_MODULE, r"web/.*\.(css|js)")

    def _setup_hooks(self) -> None:
        gui_hooks.webview_will_set_content.append(self._on_webview_content)
        gui_hooks.webview_did_receive_js_message.append(self._on_js_message)
        gui_hooks.reviewer_did_show_question.append(self._on_card_shown)
        gui_hooks.reviewer_did_show_answer.append(self._on_card_shown)
        gui_hooks.state_did_change.append(self._on_state_changed)

    def _on_webview_content(self, web_content, context) -> None:  # type: ignore[no-untyped-def]
        if not isinstance(context, ReviewerBottomBar):
            return
        package = mw.addonManager.addonFromModule(ADDON_MODULE)
        web_content.css.append(f"/_addons/{package}/web/reviewer-strip.css")
        web_content.js.append(f"/_addons/{package}/web/reviewer-strip.js")
        web_content.body += """
<div id="avf-strip" class="avf-state-starting" role="status" aria-live="polite">
  <button id="avf-record" type="button" onclick="pycmd('avf:toggle')">
    <span id="avf-record-icon" aria-hidden="true">●</span>
    <span id="avf-record-label">Record</span>
    <span class="avf-hotkey">F8</span>
  </button>
  <span id="avf-status-dot" aria-hidden="true"></span>
  <span id="avf-status">Starting voice helper...</span>
  <span id="avf-field" title="Destination field">No target field</span>
  <span id="avf-queue" title="Pending voice notes">Queue 0</span>
  <label id="avf-review-label" title="Review each transcript before saving">
    <input id="avf-review" type="checkbox" checked
      onchange="pycmd('avf:review:' + (this.checked ? '1' : '0'))">
    Review
  </label>
  <button id="avf-action" type="button" hidden onclick="pycmd('avf:context')"></button>
</div>
"""

    def _on_js_message(self, handled, message: str, context):  # type: ignore[no-untyped-def]
        if not isinstance(context, ReviewerBottomBar) or not message.startswith("avf:"):
            return handled
        if message == "avf:toggle":
            self.toggle_recording()
        elif message.startswith("avf:review:"):
            self.set_review_before_save(message.endswith(":1"))
        elif message == "avf:context":
            if self.setup_required:
                self.launch_setup()
            elif self.protocol_mismatch:
                self.show_details()
            elif self.helper_state.get("phase") == "offline":
                self.ensure_helper_started()
            else:
                self.show_details()
        return (True, None)

    def _on_card_shown(self, card) -> None:  # type: ignore[no-untyped-def]
        try:
            note = card.note()
            config = self.config()
            field_name = self._choose_target_field(note, config)
            self.current_target = {
                "card_id": int(card.id),
                "note_id": int(note.id),
                "field_name": field_name,
                "deck_name": str(mw.col.decks.name(card.did)),
                "label": self._note_label(note, field_name),
            }
            self.target_error = ""
        except (KeyError, TypeError, ValueError) as exc:
            self.current_target = None
            self.target_error = str(exc)
        self.push_ui_state()

    def _on_state_changed(self, new_state: str, old_state: str) -> None:
        if new_state != "review":
            self.current_target = None
            self.target_error = "Start reviewing a card first."
        else:
            QTimer.singleShot(50, self.push_ui_state)

    def _choose_target_field(self, note, config: dict[str, Any]) -> str:  # type: ignore[no-untyped-def]
        field_names = list(note.keys())
        preferred = str(config["target_field_name"])
        if preferred in field_names:
            return preferred

        model = note.note_type()
        model_name = str(model.get("name", "")) if isinstance(model, dict) else ""
        hints = [str(hint).casefold() for hint in config["image_occlusion_model_hints"]]
        image_field = str(config["image_occlusion_fallback_field_name"])
        if any(hint in model_name.casefold() for hint in hints) and image_field in field_names:
            return image_field

        for candidate in config["default_fallback_field_names"]:
            candidate = str(candidate)
            if candidate in field_names:
                return candidate
        available = ", ".join(field_names) if field_names else "none"
        raise ValueError(f"No usable voice-note field. Available: {available}")

    @staticmethod
    def _note_label(note, target_field: str) -> str:  # type: ignore[no-untyped-def]
        field_names = list(note.keys())
        preferred = ["Front", "Text", "Question", *field_names]
        for name in preferred:
            if name == target_field or name not in field_names:
                continue
            raw = str(note[name])
            text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
            text = " ".join(text.split())
            if text:
                return text[:120]
        return ""

    def _run_command(self, command: Callable[[], dict[str, Any]]) -> None:
        if self.command_in_flight:
            return
        self.command_in_flight = True
        self.push_ui_state()

        def done(future: Future) -> None:
            self.command_in_flight = False
            try:
                payload = dict(future.result())
            except Exception as exc:
                self.last_connection_error = str(exc)
                self._add_activity(str(exc), "Error")
                tooltip(f"Anki Voice Field: {exc}")
            else:
                message = str(payload.get("message", ""))
                if message:
                    self._add_activity(message)
                    tooltip(message)
            self.poll_state()
            self.push_ui_state()

        self.background.submit(command, done)

    def _process_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            event_type = str(event.get("type", ""))
            message = str(event.get("message", ""))
            if message:
                self._add_activity(message, event_type.replace("_", " ").title())
            if event_type in {"saved", "dry_run_complete", "error"} and message:
                tooltip(message)

    def _sync_review_dialogs(self, jobs: list[dict[str, Any]]) -> None:
        if self.active_dialog is not None:
            return
        job = self.review_gate.next_job(jobs)
        if job is not None:
            self._open_review_dialog(job)

    def _open_review_dialog(self, job: dict[str, Any]) -> None:
        job_id = str(job["job_id"])

        def dispatch(
            action: str,
            transcript: str,
            on_success: Callable[[], None],
            on_failure: Callable[[str], None],
        ) -> None:
            if action == "save":
                command = lambda: self.client.save_job(job_id, transcript)
            elif action == "rerecord":
                command = lambda: self.client.rerecord_job(job_id)
            else:
                command = lambda: self.client.cancel_job(job_id)

            def done(future: Future) -> None:
                try:
                    future.result()
                except Exception as exc:
                    on_failure(str(exc))
                    return
                self.review_gate.mark_handled(job_id)
                on_success()
                self.poll_state()

            self.background.submit(command, done)

        dialog = ReviewDialog(mw, job, dispatch)
        self.active_dialog = dialog

        def finished(_result: int) -> None:
            self.active_dialog = None
            self.review_gate.dialog_closed(job_id)

        qconnect(dialog.finished, finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _set_offline(self, message: str) -> None:
        was_offline = self.helper_state.get("phase") == "offline"
        self.helper_state.update(
            phase="offline",
            status_message=message,
            recording=False,
            queue_count=0,
            pending_reviews=[],
        )
        if not was_offline or self.last_revision != -2:
            self.last_revision = -2
            self.push_ui_state()

    def _setup_config_action(self) -> None:
        mw.addonManager.setConfigAction(ADDON_MODULE, self.open_settings)

    def _setup_hotkey(self) -> None:
        hotkey = str(self.config()["hotkey"]).strip()
        if not hotkey:
            return
        shortcut = QShortcut(QKeySequence(hotkey), mw)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)

        def activated() -> None:
            if mw.state == "review" or bool(self.helper_state.get("recording")):
                self.toggle_recording()

        qconnect(shortcut.activated, activated)
        self.shortcuts.append(shortcut)

    def _rebuild_hotkey(self) -> None:
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts.clear()
        self._setup_hotkey()

    def _add_activity(self, message: str, label: str = "Info") -> None:
        message = " ".join(str(message).split())
        if not message:
            return
        self.recent_activity.append(
            f"{time.strftime('%H:%M:%S')}  {label}: {message}"
        )
        self._refresh_settings_dialog()

    def _refresh_settings_dialog(self) -> None:
        dialog = self.settings_dialog
        if dialog is None:
            return
        recording = bool(self.helper_state.get("recording", False))
        helper_target = self.helper_state.get("current_target")
        target = (
            helper_target
            if recording and isinstance(helper_target, dict)
            else self.current_target
        )
        if isinstance(target, dict) and target.get("field_name"):
            destination = str(target["field_name"])
            if target.get("deck_name"):
                destination += f" ({target['deck_name']})"
        else:
            destination = self.target_error or "Start reviewing a card."
        phase = str(self.helper_state.get("phase", "offline"))
        can_record = (
            not self.command_in_flight
            and self.current_target is not None
            and phase not in {"offline", "starting"}
        )
        dialog.refresh_status(
            phase=phase,
            status=str(
                self.helper_state.get("status_message", "Voice helper is offline.")
            ),
            model_state=str(self.helper_state.get("model_state", "unknown")),
            destination=destination,
            queue_count=int(self.helper_state.get("queue_count", 0)),
            recording=recording,
            can_record=can_record,
            activity=list(self.recent_activity),
        )


_controller: NativeVoiceController | None = None


def initialize() -> NativeVoiceController:
    global _controller
    if _controller is None:
        _controller = NativeVoiceController()
    return _controller
