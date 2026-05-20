from datetime import datetime
import unittest
from pathlib import Path

import config
from anki_client import (
    choose_target_field,
    append_transcript_to_field,
    field_contains_appended_transcript,
)
from session_log import append_saved_voice_note
from transcriber import build_transcription_options


class AppendFormatTests(unittest.TestCase):
    def test_append_transcript_to_empty_field(self) -> None:
        timestamp = datetime(2026, 5, 11, 18, 30)

        result = append_transcript_to_field("", "transcribed text here", timestamp)

        self.assertEqual(
            result,
            (
                "<hr>\n"
                "<b>Voice Note - 2026-05-11 18:30</b><br>\n"
                "transcribed text here"
            ),
        )

    def test_append_transcript_preserves_existing_field(self) -> None:
        timestamp = datetime(2026, 5, 11, 18, 30)
        existing = "older lecture notes"

        result = append_transcript_to_field(existing, "new voice note", timestamp)

        self.assertEqual(
            result,
            (
                "older lecture notes\n"
                "<hr>\n"
                "<b>Voice Note - 2026-05-11 18:30</b><br>\n"
                "new voice note"
            ),
        )

    def test_append_transcript_escapes_html(self) -> None:
        timestamp = datetime(2026, 5, 11, 18, 30)

        result = append_transcript_to_field(
            "",
            "less than < greater than > and don't escape apostrophes",
            timestamp,
        )

        self.assertIn("less than &lt; greater than &gt;", result)
        self.assertIn("don't escape apostrophes", result)

    def test_verify_appended_transcript_allows_html_normalization(self) -> None:
        timestamp = datetime(2026, 5, 11, 18, 30)
        field_html = (
            "old notes"
            "<hr><b>Voice Note - 2026-05-11 18:30</b><br/>"
            "line one<br/>line two"
        )

        self.assertTrue(
            field_contains_appended_transcript(
                field_html,
                "line one\nline two",
                timestamp,
            )
        )

    def test_session_log_writes_saved_voice_note(self) -> None:
        original_path = config.VOICE_NOTES_LOG_FILE
        test_output = Path(__file__).resolve().parent / "_test_voice_notes_log.txt"

        config.VOICE_NOTES_LOG_FILE = test_output
        try:
            append_saved_voice_note(
                saved_at=datetime(2026, 5, 11, 18, 30, 12),
                card_id=123,
                note_id=456,
                field_name="Lecture Notes",
                transcript="test transcript",
            )

            contents = config.VOICE_NOTES_LOG_FILE.read_text(encoding="utf-8")
        finally:
            config.VOICE_NOTES_LOG_FILE = original_path

        self.assertIn("Saved: 2026-05-11 18:30:12", contents)
        self.assertIn("Card ID: 123", contents)
        self.assertIn("Note ID: 456", contents)
        self.assertIn("Field: Lecture Notes", contents)
        self.assertIn("test transcript", contents)

    def test_choose_target_field_prefers_lecture_notes(self) -> None:
        fields = {"Back": "", "Lecture Notes": ""}

        self.assertEqual(choose_target_field(fields, "Basic"), "Lecture Notes")

    def test_choose_target_field_uses_remarks_for_image_occlusion(self) -> None:
        fields = {"Back": "", "Remarks": ""}

        self.assertEqual(
            choose_target_field(fields, "Image Occlusion Enhanced"),
            "Remarks",
        )

    def test_choose_target_field_falls_back_to_back(self) -> None:
        fields = {"Front": "", "Back": ""}

        self.assertEqual(choose_target_field(fields, "Basic"), "Back")

    def test_medical_transcription_options_include_context(self) -> None:
        original_mode = config.MEDICAL_TRANSCRIPTION_MODE

        config.MEDICAL_TRANSCRIPTION_MODE = True
        try:
            options = build_transcription_options()
        finally:
            config.MEDICAL_TRANSCRIPTION_MODE = original_mode

        self.assertEqual(options["language"], "en")
        self.assertEqual(options["beam_size"], config.WHISPER_BEAM_SIZE)
        self.assertIn("medical education note", options["initial_prompt"])
        self.assertIn("hyponatremia", options["hotwords"])

    def test_medical_transcription_options_can_be_disabled(self) -> None:
        original_mode = config.MEDICAL_TRANSCRIPTION_MODE

        config.MEDICAL_TRANSCRIPTION_MODE = False
        try:
            options = build_transcription_options()
        finally:
            config.MEDICAL_TRANSCRIPTION_MODE = original_mode

        self.assertIsNone(options["initial_prompt"])
        self.assertIsNone(options["hotwords"])


if __name__ == "__main__":
    unittest.main()
