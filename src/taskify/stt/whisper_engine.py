"""Faster-Whisper Speech-to-Text engine implementation."""

from pathlib import Path
from typing import Any

import numpy as np

from taskify.config import Settings, get_default_paths
from taskify.stt.base import STTEngine


class WhisperEngine(STTEngine):
    """Fallback offline speech-to-text engine using faster-whisper (CTranslate2)."""

    def __init__(self, settings: Settings) -> None:
        """Initialize engine configurations.

        Args:
            settings (Settings): Application settings.
        """
        self._model_size = settings.stt.whisper_model
        self._language = settings.stt.language

        # Resolve local model storage path
        _, data_dir = get_default_paths()
        self._model_root = data_dir / "models" / "whisper"

        self._model: Any = None
        self._initialized = False

        # Accumulation buffer for streaming chunks
        self._audio_buffer: list[np.ndarray] = []

    @property
    def model_path(self) -> Path:
        """Get directory path where the model is stored.

        Returns:
            Path: Model directory.
        """
        return self._model_root / f"models--Systran--faster-whisper-{self._model_size}"

    def initialize(self) -> None:
        """Load the faster-whisper model into memory on CPU.

        Raises:
            RuntimeError: If loading model files fails.
        """
        if self._initialized:
            return

        # Lazy import to avoid loading heavy deep learning libraries on CLI launch
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ImportError(
                "faster-whisper is not installed. "
                'Install it using: pip install "taskify[whisper]"'
            ) from e

        # Ensure directory is created
        self._model_root.mkdir(parents=True, exist_ok=True)

        try:
            # Load model on CPU with int8 quantization for speed and RAM efficiency
            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
                download_root=str(self._model_root),
            )
            self._initialized = True
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {e}") from e

    def transcribe_chunk(self, chunk: np.ndarray) -> str | None:
        """Accumulate incoming audio chunks for batch processing on flush.

        Args:
            chunk (np.ndarray): Mono float32 audio chunk.

        Returns:
            str, optional: Always None; Whisper is not a frame-by-frame streaming model.
        """
        if not self._initialized:
            raise RuntimeError("Whisper engine is not initialized.")

        self._audio_buffer.append(chunk)
        return None

    def flush(self) -> str | None:
        """Concatenate buffered audio and run Whisper batch transcription.

        Returns:
            str, optional: Full transcribed text string if speech detected.
        """
        if not self._initialized:
            return None

        if not self._audio_buffer:
            return None

        # Concatenate float32 frames
        audio_data = np.concatenate(self._audio_buffer)
        self._audio_buffer.clear()

        try:
            # Run inference
            segments, _ = self._model.transcribe(
                audio_data,
                language=self._language,
                beam_size=5,
            )

            # segments is a generator; exhaust it to join texts
            phrases = [seg.text for seg in segments]
            text = " ".join(phrases).strip()
            return text if text else None
        except Exception as e:
            # Fallback returning None on inference crashes
            print(f"Warning: Whisper inference failed: {e}")
            return None

    def is_initialized(self) -> bool:
        """Check if model is loaded.

        Returns:
            bool: True if initialized.
        """
        return self._initialized
