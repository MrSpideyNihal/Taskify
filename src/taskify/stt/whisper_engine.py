"""Faster-Whisper Speech-to-Text engine implementation.

Provides high-accuracy offline transcription using CTranslate2-quantized
Whisper models. Implements VAD-based pseudo-streaming to deliver
transcription results during active recording rather than only on flush.
"""

from pathlib import Path
from typing import Any

import numpy as np

from taskify.config import Settings, get_default_paths
from taskify.stt.base import STTEngine


class WhisperEngine(STTEngine):
    """Fallback offline speech-to-text engine using faster-whisper (CTranslate2).

    Unlike Vosk, Whisper is not a frame-by-frame streaming model. To provide
    near-real-time results, this engine accumulates audio and uses simple
    Voice Activity Detection (VAD) to segment speech at natural pauses.
    When a pause is detected, the buffered segment is transcribed and
    returned immediately.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize engine configurations.

        Args:
            settings (Settings): Application settings.
        """
        self._model_size = settings.stt.whisper_model
        self._language = settings.stt.language
        self._sample_rate = settings.audio.sample_rate

        # Resolve local model storage path
        _, data_dir = get_default_paths()
        self._model_root = data_dir / "models" / "whisper"

        self._model: Any = None
        self._initialized = False

        # Accumulation buffer for streaming chunks
        self._audio_buffer: list[np.ndarray] = []

        # VAD parameters for pseudo-streaming
        self._vad_threshold = settings.audio.silence_threshold
        self._chunk_duration_s = settings.audio.chunk_duration_ms / 1000.0
        # Require 1.2 seconds of silence to trigger a segment boundary
        self._vad_silence_chunks = max(
            1, int(1.2 / self._chunk_duration_s)
        )
        self._silent_count = 0
        self._has_speech = False
        # Minimum segment length in seconds before we consider transcribing
        self._min_segment_s = 0.8

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

    def _transcribe_buffer(self) -> str | None:
        """Run Whisper inference on the accumulated audio buffer.

        Concatenates all buffered chunks, clears the buffer, and returns
        the transcribed text.

        Returns:
            str, optional: Transcribed text if speech detected, else None.
        """
        if not self._audio_buffer:
            return None

        # Concatenate float32 frames
        audio_data = np.concatenate(self._audio_buffer)
        self._audio_buffer.clear()
        self._silent_count = 0
        self._has_speech = False

        # Skip very short segments (< min_segment_s) to avoid junk output
        segment_duration = len(audio_data) / self._sample_rate
        if segment_duration < self._min_segment_s:
            return None

        try:
            # Run inference
            segments, _ = self._model.transcribe(
                audio_data,
                language=self._language,
                beam_size=5,
                vad_filter=True,
            )

            # segments is a generator; exhaust it to join texts
            phrases = [seg.text for seg in segments]
            text = " ".join(phrases).strip()
            return text if text else None
        except Exception as e:
            # Fallback returning None on inference crashes
            print(f"Warning: Whisper inference failed: {e}")
            return None

    def transcribe_chunk(self, chunk: np.ndarray) -> str | None:
        """Process an audio chunk with VAD-based segmentation.

        Accumulates audio and monitors silence levels. When a natural
        speech pause is detected (sustained silence after speech), the
        accumulated segment is transcribed and returned immediately.

        Args:
            chunk (np.ndarray): Mono float32 audio chunk.

        Returns:
            str, optional: Transcribed text at speech boundaries, else None.
        """
        if not self._initialized:
            raise RuntimeError("Whisper engine is not initialized.")

        self._audio_buffer.append(chunk)

        # Compute RMS energy for VAD
        rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) > 0 else 0.0

        if rms >= self._vad_threshold:
            # Speech detected
            self._has_speech = True
            self._silent_count = 0
            return None
        else:
            # Silence detected
            self._silent_count += 1

            if self._has_speech and self._silent_count >= self._vad_silence_chunks:
                # Natural pause after speech -- transcribe the segment
                return self._transcribe_buffer()

            return None

    def flush(self) -> str | None:
        """Concatenate buffered audio and run Whisper batch transcription.

        Returns:
            str, optional: Full transcribed text string if speech detected.
        """
        if not self._initialized:
            return None

        return self._transcribe_buffer()

    def is_initialized(self) -> bool:
        """Check if model is loaded.

        Returns:
            bool: True if initialized.
        """
        return self._initialized
