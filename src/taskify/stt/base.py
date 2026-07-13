"""Abstract speech-to-text engine base class."""

from abc import ABC, abstractmethod

import numpy as np


class STTEngine(ABC):
    """Abstract interface defining required behaviors for local speech transcribers."""

    @abstractmethod
    def initialize(self) -> None:
        """Load transcription model resources into memory.

        Raises:
            RuntimeError: If loading model files fails.
        """
        pass

    @abstractmethod
    def transcribe_chunk(self, chunk: np.ndarray) -> str | None:
        """Process a single raw audio chunk.

        Args:
            chunk (np.ndarray): Mono float32 audio array.

        Returns:
            str, optional: Transcribed phrase if boundary detected, else None.
        """
        pass

    @abstractmethod
    def flush(self) -> str | None:
        """Flush pending active transcription buffers.

        Returns:
            str, optional: Remaining transcribed phrase if present.
        """
        pass

    @abstractmethod
    def is_initialized(self) -> bool:
        """Determine if engine model is loaded.

        Returns:
            bool: True if initialized.
        """
        pass
