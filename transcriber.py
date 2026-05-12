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


def transcribe_audio(audio_path: Path) -> str:
    model = get_model()
    segments, _info = model.transcribe(str(audio_path), beam_size=1)
    transcript = " ".join(segment.text.strip() for segment in segments).strip()

    if not transcript:
        raise TranscriptionError("No speech was transcribed from the recording.")
    return transcript
