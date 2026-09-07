from __future__ import annotations

from typing import Any, Callable

from aqt.qt import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


SaveSettings = Callable[[dict[str, Any]], None]


class VoiceSettingsDialog(QDialog):
    """Native Anki settings and status panel for Anki Voice Field."""

    def __init__(
        self,
        parent: QWidget,
        config: dict[str, Any],
        *,
        save_settings: SaveSettings,
        toggle_recording: Callable[[], None],
        test_connection: Callable[[], None],
        retry_helper: Callable[[], None],
        show_details: Callable[[], None],
        open_legacy_client: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._save_settings = save_settings

        self.setWindowTitle("Anki Voice Field Settings")
        self.resize(760, 680)
        self.setMinimumSize(660, 560)

        root = QVBoxLayout(self)

        heading = QLabel("Anki Voice Field v2")
        heading.setStyleSheet("font-size: 18px; font-weight: 650;")
        root.addWidget(heading)

        description = QLabel(
            "Record, review, and save voice notes without leaving Anki. "
            "The speech model runs silently in the background."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        status_group = QGroupBox("Live status")
        status_layout = QGridLayout(status_group)
        status_layout.addWidget(QLabel("State"), 0, 0)
        self.state_value = QLabel("Starting")
        self.state_value.setStyleSheet("font-weight: 600;")
        status_layout.addWidget(self.state_value, 0, 1)
        status_layout.addWidget(QLabel("Model"), 0, 2)
        self.model_value = QLabel("Loading")
        status_layout.addWidget(self.model_value, 0, 3)

        status_layout.addWidget(QLabel("Destination"), 1, 0)
        self.destination_value = QLabel("Start reviewing a card")
        self.destination_value.setWordWrap(True)
        status_layout.addWidget(self.destination_value, 1, 1)
        status_layout.addWidget(QLabel("Queue"), 1, 2)
        self.queue_value = QLabel("0")
        status_layout.addWidget(self.queue_value, 1, 3)

        self.status_message = QLabel("Starting voice helper...")
        self.status_message.setWordWrap(True)
        status_layout.addWidget(self.status_message, 2, 0, 1, 4)

        control_row = QHBoxLayout()
        self.record_button = QPushButton("Start Recording")
        self.test_button = QPushButton("Test Anki")
        self.retry_button = QPushButton("Start / Retry Helper")
        self.details_button = QPushButton("Details")
        self.record_button.clicked.connect(toggle_recording)
        self.test_button.clicked.connect(test_connection)
        self.retry_button.clicked.connect(retry_helper)
        self.details_button.clicked.connect(show_details)
        control_row.addWidget(self.record_button)
        control_row.addWidget(self.test_button)
        control_row.addWidget(self.retry_button)
        control_row.addWidget(self.details_button)
        control_row.addStretch(1)
        status_layout.addLayout(control_row, 3, 0, 1, 4)
        root.addWidget(status_group)

        behavior_group = QGroupBox("Recording behavior")
        behavior_layout = QFormLayout(behavior_group)
        self.review_checkbox = QCheckBox("Open the native transcript editor before saving")
        self.review_checkbox.setChecked(bool(config["review_before_save"]))
        behavior_layout.addRow("Review before saving", self.review_checkbox)

        self.dry_run_checkbox = QCheckBox("Transcribe and preview without changing the note")
        self.dry_run_checkbox.setChecked(bool(config["dry_run"]))
        behavior_layout.addRow("Dry run", self.dry_run_checkbox)

        self.auto_start_checkbox = QCheckBox("Start the hidden voice service when needed")
        self.auto_start_checkbox.setChecked(bool(config["auto_start_helper"]))
        behavior_layout.addRow("Automatic helper", self.auto_start_checkbox)

        self.launch_on_startup_checkbox = QCheckBox("Preload the voice service when Anki starts")
        self.launch_on_startup_checkbox.setChecked(
            bool(config["auto_launch_helper_on_anki_startup"])
        )
        behavior_layout.addRow("Preload on startup", self.launch_on_startup_checkbox)

        self.hotkey_edit = QLineEdit(str(config["hotkey"]))
        self.hotkey_edit.setPlaceholderText("F8")
        behavior_layout.addRow("Record / Stop hotkey", self.hotkey_edit)
        root.addWidget(behavior_group)

        fields_group = QGroupBox("Automatic destination field")
        fields_layout = QFormLayout(fields_group)
        self.preferred_field_edit = QLineEdit(str(config["target_field_name"]))
        fields_layout.addRow("Preferred field", self.preferred_field_edit)
        self.image_field_edit = QLineEdit(
            str(config["image_occlusion_fallback_field_name"])
        )
        fields_layout.addRow("Image Occlusion field", self.image_field_edit)
        self.fallback_fields_edit = QLineEdit(
            ", ".join(str(value) for value in config["default_fallback_field_names"])
        )
        fields_layout.addRow("Fallback fields", self.fallback_fields_edit)
        root.addWidget(fields_group)

        activity_group = QGroupBox("Recent activity")
        activity_layout = QVBoxLayout(activity_group)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumBlockCount(150)
        self.activity_log.setPlaceholderText(
            "Recording, transcription, save, and error messages will appear here."
        )
        activity_layout.addWidget(self.activity_log)
        root.addWidget(activity_group, 1)

        advanced_row = QHBoxLayout()
        advanced_label = QLabel("Advanced troubleshooting")
        self.legacy_button = QPushButton("Open Legacy Helper")
        self.legacy_button.setToolTip(
            "Optional troubleshooting client. Normal use should stay inside Anki."
        )
        self.legacy_button.clicked.connect(open_legacy_client)
        advanced_row.addWidget(advanced_label)
        advanced_row.addStretch(1)
        advanced_row.addWidget(self.legacy_button)
        root.addLayout(advanced_row)

        bottom_row = QHBoxLayout()
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #b3261e;")
        self.error_label.setWordWrap(True)
        self.save_button = QPushButton("Save Settings")
        close_button = QPushButton("Close")
        self.save_button.clicked.connect(self._save)
        close_button.clicked.connect(self.reject)
        bottom_row.addWidget(self.error_label, 1)
        bottom_row.addWidget(self.save_button)
        bottom_row.addWidget(close_button)
        root.addLayout(bottom_row)

    def _save(self) -> None:
        preferred = self.preferred_field_edit.text().strip()
        image_field = self.image_field_edit.text().strip()
        fallbacks = [
            value.strip()
            for value in self.fallback_fields_edit.text().split(",")
            if value.strip()
        ]
        if not preferred:
            self._show_error("Preferred field cannot be empty.")
            return
        if not image_field:
            self._show_error("Image Occlusion field cannot be empty.")
            return
        if not fallbacks:
            self._show_error("Enter at least one fallback field.")
            return

        self._show_error("")
        self._save_settings(
            {
                "review_before_save": self.review_checkbox.isChecked(),
                "dry_run": self.dry_run_checkbox.isChecked(),
                "auto_start_helper": self.auto_start_checkbox.isChecked(),
                "auto_launch_helper_on_anki_startup": (
                    self.launch_on_startup_checkbox.isChecked()
                ),
                "hotkey": self.hotkey_edit.text().strip(),
                "target_field_name": preferred,
                "image_occlusion_fallback_field_name": image_field,
                "default_fallback_field_names": fallbacks,
            }
        )

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)

    def refresh_status(
        self,
        *,
        phase: str,
        status: str,
        model_state: str,
        destination: str,
        queue_count: int,
        recording: bool,
        can_record: bool,
        activity: list[str],
    ) -> None:
        state_labels = {
            "ready": "Ready",
            "recording": "Recording",
            "transcribing": "Transcribing",
            "waiting_review": "Waiting for review",
            "saving": "Saving",
            "queued": "Queued",
            "starting": "Starting",
            "offline": "Offline",
            "error": "Error",
        }
        self.state_value.setText(state_labels.get(phase, phase.replace("_", " ").title()))
        self.model_value.setText(model_state.replace("_", " ").title())
        self.destination_value.setText(destination)
        self.queue_value.setText(str(queue_count))
        self.status_message.setText(status)
        self.record_button.setText("Stop Recording" if recording else "Start Recording")
        self.record_button.setEnabled(recording or can_record)
        self.activity_log.setPlainText("\n".join(activity))
        scrollbar = self.activity_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
