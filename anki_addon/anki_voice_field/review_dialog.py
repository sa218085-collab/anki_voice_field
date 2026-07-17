from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aqt.qt import (
    QDialog,
    QHBoxLayout,
    QKeySequence,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QVBoxLayout,
    QWidget,
)


ActionDone = Callable[[], None]
ActionFailed = Callable[[str], None]
ActionDispatcher = Callable[[str, str, ActionDone, ActionFailed], None]


class ReviewDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        job: dict[str, Any],
        dispatch: ActionDispatcher,
    ) -> None:
        super().__init__(parent)
        self.job = job
        self.dispatch = dispatch
        self._resolved = False
        self._busy = False

        self.setWindowTitle("Review Voice Note")
        self.resize(660, 390)

        layout = QVBoxLayout(self)
        field_name = str(job.get("field_name", "unknown"))
        title = QLabel(f'Review before appending to “{field_name}”')
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        details: list[str] = []
        if job.get("deck_name"):
            details.append(str(job["deck_name"]))
        if job.get("label"):
            details.append(str(job["label"]))
        if not details:
            details.append(f"Note {job.get('note_id', 'unknown')}")
        metadata = QLabel(" · ".join(details))
        metadata.setWordWrap(True)
        layout.addWidget(metadata)

        self.error_label = QLabel(str(job.get("error", "")))
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b3261e;")
        self.error_label.setVisible(bool(job.get("error")))
        layout.addWidget(self.error_label)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(str(job.get("transcript", "")))
        self.editor.setPlaceholderText("Transcript")
        layout.addWidget(self.editor, 1)

        button_row = QHBoxLayout()
        self.save_button = QPushButton(
            "Close Preview" if bool(job.get("dry_run")) else "Save To Anki"
        )
        self.rerecord_button = QPushButton("Re-record")
        self.cancel_button = QPushButton("Cancel")
        self.save_button.clicked.connect(lambda: self._submit("save"))
        self.rerecord_button.clicked.connect(lambda: self._submit("rerecord"))
        self.cancel_button.clicked.connect(lambda: self._submit("cancel"))
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.rerecord_button)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(lambda: self._submit("save"))
        self._shortcut = shortcut
        self.editor.setFocus()

    @property
    def job_id(self) -> str:
        return str(self.job["job_id"])

    def _submit(self, action: str) -> None:
        if self._busy or self._resolved:
            return
        transcript = self.editor.toPlainText().strip()
        if action == "save" and not transcript:
            self._show_error("Transcript cannot be empty.")
            return

        self._set_busy(True)

        def done() -> None:
            self._resolved = True
            self.accept()

        def failed(message: str) -> None:
            self._set_busy(False)
            self._show_error(message)

        self.dispatch(action, transcript, done, failed)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.save_button.setEnabled(not busy)
        self.rerecord_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        self.editor.setEnabled(not busy)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._resolved:
            event.accept()
            return
        if self._busy:
            event.ignore()
            return
        event.ignore()
        self._submit("cancel")
