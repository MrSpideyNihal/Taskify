"""Vosk Speech-to-Text engine implementation."""

import json
from pathlib import Path
from typing import Any

import numpy as np

from taskify.config import Settings, get_default_paths
from taskify.stt.base import STTEngine


class VoskEngine(STTEngine):
    """Primary offline speech-to-text engine using Vosk Kaldi speech models."""

    def __init__(self, settings: Settings) -> None:
        """Initialize engine configurations.

        Args:
            settings (Settings): Application settings.
        """
        self._model_name = settings.stt.vosk_model
        self._sample_rate = settings.audio.sample_rate

        # Resolve local model storage path
        _, data_dir = get_default_paths()
        # Look in default path (could be small-en, large-en etc.)
        self._model_root = data_dir / "models" / "vosk"

        self._model: Any = None
        self._recognizer: Any = None
        self._initialized = False

    @property
    def model_path(self) -> Path:
        """Get target directory path for the current model.

        Returns:
            Path: Model file path.
        """
        # Map simple identifier to directory name matching the downloader
        from taskify.stt.download import VOSK_MODEL_URLS

        if self._model_name in VOSK_MODEL_URLS:
            url = VOSK_MODEL_URLS[self._model_name]
            folder_name = url.split("/")[-1].replace(".zip", "")
            return self._model_root / folder_name

        # If custom model name, assume directory name matches directly
        return self._model_root / self._model_name

    def initialize(self) -> None:
        """Load Vosk model directory and initialize KaldiRecognizer.

        Raises:
            RuntimeError: If model folder is not found or fails to load.
        """
        if self._initialized:
            return

        model_dir = self.model_path
        if not model_dir.exists() or not model_dir.is_dir():
            raise RuntimeError(
                f"Vosk model not found at: {model_dir}. Please run "
                f"'taskify download-model --engine vosk "
                f"--model {self._model_name}' first."
            )

        # Lazy import to avoid loading heavy modules on CLI launch
        import vosk

        # Suppress Kaldi logs outputting directly to stderr to keep CLI/GUI clean
        vosk.SetLogLevel(-1)

        try:
            self._model = vosk.Model(str(model_dir))
            self._recognizer = vosk.KaldiRecognizer(self._model, self._sample_rate)
            self._initialized = True
        except Exception as e:
            raise RuntimeError(f"Failed to load Vosk model: {e}") from e

    def transcribe_chunk(self, chunk: np.ndarray) -> str | None:
        """Convert float32 audio chunk to 16-bit PCM and transcribe.

        Args:
            chunk (np.ndarray): Mono audio array.

        Returns:
            str, optional: Transcribed phrase if boundary detected.
        """
        if not self._initialized:
            raise RuntimeError("Vosk engine is not initialized.")

        # Scale float32 (-1.0 to 1.0) to signed 16-bit integers
        pcm_chunk = np.clip(chunk * 32767.0, -32768.0, 32767.0).astype(np.int16)
        pcm_bytes = pcm_chunk.tobytes()

        # Feed recognizer
        if self._recognizer.AcceptWaveform(pcm_bytes):
            res_json = self._recognizer.Result()
            try:
                res_data = json.loads(res_json)
                text = res_data.get("text", "").strip()
                return text if text else None
            except json.JSONDecodeError:
                return None
        return None

    def flush(self) -> str | None:
        """Process remaining audio buffer and extract final transcript.

        Returns:
            str, optional: Transcribed phrase.
        """
        if not self._initialized:
            return None

        res_json = self._recognizer.FinalResult()
        try:
            res_data = json.loads(res_json)
            text = res_data.get("text", "").strip()
            return text if text else None
        except json.JSONDecodeError:
            return None

    def is_initialized(self) -> bool:
        """Check if model is loaded.

        Returns:
            bool: True if initialized.
        """
        return self._initialized
