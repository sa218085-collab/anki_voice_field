from __future__ import annotations

import html
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from aqt import mw
from aqt.qt import QAction, QKeySequence, QShortcut
from aqt.utils import getText, qconnect, showInfo, tooltip


DEFAULT_CONFIG = {
    "helper_project_folder": "__BUNDLED__",
    "helper_pythonw_path": "__AUTO__",
    "control_url": "http://127.0.0.1:47866",
    "hotkey": "F8",
    "auto_start_helper": True,
    "show_advanced_menu_items": False,
    "target_field_name": "Lecture Notes",
    "image_occlusion_model_hints": ["Image Occlusion"],
    "image_occlusion_fallback_field_name": "Remarks",
    "default_fallback_field_names": ["Back", "Extra", "Back Extra", "Remarks"],
}

_shortcuts: list[QShortcut] = []
_actions: list[QAction] = []


def addon_folder() -> Path:
    return Path(__file__).resolve().parent


def addon_config() -> dict[str, Any]:
    config = mw.addonManager.getConfig(__name__)
    if not isinstance(config, dict):
        return DEFAULT_CONFIG.copy()

    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged


def resolve_helper_project_folder(config: dict[str, Any]) -> Path:
    raw_folder = str(config["helper_project_folder"]).strip()
    if not raw_folder or raw_folder == "__BUNDLED__":
        return addon_folder() / "helper"
    return Path(raw_folder)


def resolve_helper_pythonw_path(config: dict[str, Any], project_folder: Path) -> Path:
    raw_path = str(config["helper_pythonw_path"]).strip()
    if not raw_path or raw_path == "__AUTO__":
        return project_folder / ".venv" / "Scripts" / "pythonw.exe"
    return Path(raw_path)


def control_url(path: str) -> str:
    base_url = str(addon_config()["control_url"]).rstrip("/")
    return f"{base_url}{path}"


def helper_request(path: str, *, timeout: float = 2.0) -> dict[str, Any]:
    request = urllib.request.Request(
        control_url(path),
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return dict(json_loads(response.read().decode("utf-8")))


def json_loads(text: str) -> Any:
    import json

    return json.loads(text)


def helper_is_running() -> bool:
    try:
        helper_request("/health", timeout=0.8)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return True


def start_helper_process() -> bool:
    config = addon_config()
    project_folder = resolve_helper_project_folder(config)
    pythonw_path = resolve_helper_pythonw_path(config, project_folder)
    launcher_path = project_folder / "launcher.pyw"

    if not project_folder.exists():
        showInfo(f"Helper project folder was not found:\n\n{project_folder}")
        return False
    if not pythonw_path.exists():
        return start_helper_setup(project_folder)
    if not (project_folder / "requirements.txt").exists():
        showInfo(f"Helper requirements file was not found:\n\n{project_folder}")
        return False
    if not launcher_path.exists():
        showInfo(f"Helper launcher was not found:\n\n{launcher_path}")
        return False

    args = [
        str(pythonw_path),
        str(launcher_path),
        "--start-minimized",
        "--disable-global-hotkey",
    ]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(args, cwd=str(project_folder), creationflags=creationflags)
    return True


def start_helper_setup(project_folder: Path) -> bool:
    setup_script = project_folder / "setup_helper_env.ps1"
    if not setup_script.exists():
        showInfo(
            "Helper Python environment is not ready, and the setup script was "
            f"not found:\n\n{setup_script}"
        )
        return False

    subprocess.Popen(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(setup_script),
        ],
        cwd=str(project_folder),
    )
    showInfo(
        "First-time setup has started in a PowerShell window.\n\n"
        "When it finishes, restart Anki and use Record / Stop again."
    )
    return False


def ensure_helper_running() -> bool:
    if helper_is_running():
        return True

    if not bool(addon_config()["auto_start_helper"]):
        showInfo("Anki Voice Field helper is not running.")
        return False

    if not start_helper_process():
        return False

    deadline = time.monotonic() + 10.0
    while time.monotonic() <= deadline:
        if helper_is_running():
            return True
        time.sleep(0.25)

    showInfo("Helper was started, but its control server did not become ready.")
    return False


def send_helper_command(path: str, fallback_message: str) -> None:
    if not ensure_helper_running():
        return

    try:
        response = helper_request(path)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        showInfo(f"Could not reach Anki Voice Field helper:\n\n{exc}")
        return

    message = str(response.get("message", fallback_message))
    tooltip(message)


def toggle_recording_from_anki() -> None:
    send_helper_command("/toggle", "Voice note toggled.")


def show_helper_window() -> None:
    send_helper_command("/show", "Anki Voice Field helper shown.")


def test_anki_from_helper() -> None:
    send_helper_command("/test-anki", "Anki Voice Field: Test Anki queued.")


def model_name_for_note(note: Any) -> str:
    try:
        note_type = note.note_type()
    except AttributeError:
        note_type = note.model()

    if isinstance(note_type, dict):
        return str(note_type.get("name", ""))
    return ""


def is_image_occlusion_model(model_name: str, config: dict[str, Any]) -> bool:
    normalized_model = model_name.casefold()
    hints = config["image_occlusion_model_hints"]
    return any(str(hint).casefold() in normalized_model for hint in hints)


def choose_target_field(note: Any, config: dict[str, Any]) -> str:
    field_names = list(note.keys())
    target_field_name = str(config["target_field_name"])

    if target_field_name in field_names:
        return target_field_name

    image_occlusion_field = str(config["image_occlusion_fallback_field_name"])
    if (
        is_image_occlusion_model(model_name_for_note(note), config)
        and image_occlusion_field in field_names
    ):
        return image_occlusion_field

    for field_name in config["default_fallback_field_names"]:
        field_name = str(field_name)
        if field_name in field_names:
            return field_name

    available = ", ".join(field_names) if field_names else "(none)"
    raise ValueError(f"No usable target field found. Available fields: {available}")


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


def current_reviewer_card() -> Any | None:
    reviewer = getattr(mw, "reviewer", None)
    if reviewer is None:
        return None
    return getattr(reviewer, "card", None)


def append_typed_note_to_current_card() -> None:
    card = current_reviewer_card()
    if card is None:
        showInfo("No active reviewer card found. Start reviewing a card first.")
        return

    text, accepted = getText(
        "Debug text to append to the current card's note:",
        title="Anki Voice Field",
    )
    if not accepted or not text.strip():
        return

    note = card.note()
    config = addon_config()

    try:
        field_name = choose_target_field(note, config)
        existing_value = str(note[field_name])
        updated_value = append_transcript_to_field(existing_value, text.strip())
    except ValueError as exc:
        showInfo(str(exc))
        return

    note[field_name] = updated_value
    mw.col.update_note(note)

    showInfo(
        f'Appended {len(updated_value) - len(existing_value)} characters '
        f'to "{field_name}".'
    )


def add_tools_action(label: str, callback: Any) -> QAction:
    action = QAction(label, mw)
    qconnect(action.triggered, callback)
    mw.form.menuTools.addAction(action)
    _actions.append(action)
    return action


def setup_menu_actions() -> None:
    add_tools_action("Anki Voice Field: Record / Stop", toggle_recording_from_anki)

    if not bool(addon_config()["show_advanced_menu_items"]):
        return

    add_tools_action("Anki Voice Field: Show Helper Window", show_helper_window)
    add_tools_action("Anki Voice Field: Test Connection", test_anki_from_helper)
    add_tools_action("Anki Voice Field: Append Typed Note", append_typed_note_to_current_card)


def setup_hotkey() -> None:
    hotkey = str(addon_config()["hotkey"]).strip()
    if not hotkey:
        return

    shortcut = QShortcut(QKeySequence(hotkey), mw)
    qconnect(shortcut.activated, toggle_recording_from_anki)
    _shortcuts.append(shortcut)


setup_menu_actions()
setup_hotkey()
