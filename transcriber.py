from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import config


class TranscriptionError(RuntimeError):
    pass


_MODEL: Any | None = None
_MODEL_LOCK = threading.Lock()


def get_model() -> Any:
    global _MODEL

    try:
        from faster_whisper import WhisperModel
    except ModuleNotFoundError as exc:
        raise TranscriptionError(
            "Missing dependency: faster-whisper. Install requirements with "
            "`pip install -r requirements.txt`."
        ) from exc

    with _MODEL_LOCK:
        if _MODEL is None:
            _MODEL = WhisperModel(
                config.WHISPER_MODEL_SIZE,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE_TYPE,
            )
        return _MODEL


def preload_model() -> None:
    get_model()


def build_medical_prompt() -> str | None:
    if not config.MEDICAL_TRANSCRIPTION_MODE:
        return None

    glossary = ", ".join(config.MEDICAL_GLOSSARY)
    if not glossary:
        return config.MEDICAL_TRANSCRIPTION_PROMPT

    return (
        f"{config.MEDICAL_TRANSCRIPTION_PROMPT} "
        f"Expected medical terms may include: {glossary}."
    )


def build_medical_hotwords() -> str | None:
    if not config.MEDICAL_TRANSCRIPTION_MODE:
        return None

    hotwords = " ".join(config.MEDICAL_GLOSSARY).strip()
    return hotwords or None


def build_transcription_options() -> dict[str, Any]:
    language = config.WHISPER_LANGUAGE.strip() or None

    return {
        "language": language,
        "beam_size": config.WHISPER_BEAM_SIZE,
        "initial_prompt": build_medical_prompt(),
        "hotwords": build_medical_hotwords(),
    }


def transcribe_audio(audio_path: Path) -> str:
    model = get_model()
    segments, _info = model.transcribe(
        str(audio_path),
        **build_transcription_options(),
    )
    transcript = " ".join(segment.text.strip() for segment in segments).strip()

    if not transcript:
        raise TranscriptionError("No speech was transcribed from the recording.")
    return transcript
