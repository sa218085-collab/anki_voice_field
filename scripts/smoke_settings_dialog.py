from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "anki_addon" / "anki_voice_field"
sys.path.insert(0, str(ADDON))

from aqt.qt import QApplication  # noqa: E402
from settings_dialog import VoiceSettingsDialog  # noqa: E402


def main() -> None:
    app = QApplication.instance() or QApplication([])
    saved: list[dict] = []
    config = {
        "review_before_save": True,
        "dry_run": False,
        "auto_start_helper": True,
        "auto_launch_helper_on_anki_startup": True,
        "hotkey": "F8",
        "target_field_name": "Lecture Notes",
        "image_occlusion_fallback_field_name": "Remarks",
        "default_fallback_field_names": ["Back", "Extra", "Back Extra", "Remarks"],
        "show_advanced_menu_items": False,
    }
    dialog = VoiceSettingsDialog(
        None,
        config,
        save_settings=saved.append,
        toggle_recording=lambda: None,
        test_connection=lambda: None,
        retry_helper=lambda: None,
        show_details=lambda: None,
        open_legacy_client=lambda: None,
    )
    dialog.refresh_status(
        phase="ready",
        status="Ready. Press F8 to record.",
        model_state="ready",
        destination="Lecture Notes (Test Deck)",
        queue_count=2,
        recording=False,
        can_record=True,
        activity=["12:00:00  Info: Native settings smoke test."],
    )

    assert dialog.windowTitle() == "Anki Voice Field Settings"
    assert dialog.state_value.text() == "Ready"
    assert dialog.destination_value.text() == "Lecture Notes (Test Deck)"
    assert dialog.queue_value.text() == "2"
    assert dialog.record_button.isEnabled()

    dialog.dry_run_checkbox.setChecked(True)
    dialog._save()
    assert saved and saved[0]["dry_run"] is True
    assert saved[0]["review_before_save"] is True

    dialog.close()
    app.processEvents()
    print("Native Anki settings dialog smoke test passed.")


if __name__ == "__main__":
    main()
