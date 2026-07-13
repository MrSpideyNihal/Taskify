"""Factory for instantiating the configured speech-to-text engine."""

from taskify.config import Settings
from taskify.stt.base import STTEngine
from taskify.stt.vosk_engine import VoskEngine
from taskify.stt.whisper_engine import WhisperEngine


def get_stt_engine(settings: Settings) -> STTEngine:
    """Resolve and return the configured STTEngine backend.

    Args:
        settings (Settings): Application configurations.

    Returns:
        STTEngine: Configured transcription engine instance.

    Raises:
        ValueError: If an unknown engine choice is configured.
    """
    engine_choice = settings.stt.engine.lower()

    if engine_choice == "vosk":
        return VoskEngine(settings)
    elif engine_choice == "whisper":
        return WhisperEngine(settings)
    else:
        raise ValueError(f"Unknown speech-to-text engine: {settings.stt.engine}")
