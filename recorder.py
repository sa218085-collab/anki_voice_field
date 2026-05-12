from __future__ import annotations

import queue
import tempfile
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

import config


class Recorder:
    def __init__(self) -> None:
        self._chunks: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start(self) -> None:
        if self._is_recording:
            return

        self._chunks = queue.Queue()
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="float32",
            callback=self._capture_chunk,
        )
        self._stream.start()
        self._is_recording = True

    def stop(self) -> Path:
        if not self._is_recording:
            raise RuntimeError("Recorder is not running.")

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()

        self._stream = None
        self._is_recording = False

        chunks: list[np.ndarray] = []
        while not self._chunks.empty():
            chunks.append(self._chunks.get())

        if not chunks:
            raise RuntimeError("No audio was recorded.")

        audio = np.concatenate(chunks, axis=0)
        return self._write_wav(audio, self._make_output_path())

    def _capture_chunk(self, indata, frames, time_info, status) -> None:
        if status:
            print(f"Audio warning: {status}")
        self._chunks.put(indata.copy())

    @staticmethod
    def _make_output_path() -> Path:
        config.AUDIO_TEMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            delete=False,
            dir=config.AUDIO_TEMP_FILE.parent,
            prefix=f"{config.AUDIO_TEMP_FILE.stem}_",
            suffix=config.AUDIO_TEMP_FILE.suffix,
        ) as temp_file:
            return Path(temp_file.name)

    @staticmethod
    def _write_wav(audio: np.ndarray, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        pcm_audio = np.clip(audio, -1.0, 1.0)
        pcm_audio = (pcm_audio * 32767).astype(np.int16)

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(config.CHANNELS)
            wav_file.setsampwidth(2)
            wav_file.setframerate(config.SAMPLE_RATE)
            wav_file.writeframes(pcm_audio.tobytes())

        return output_path
