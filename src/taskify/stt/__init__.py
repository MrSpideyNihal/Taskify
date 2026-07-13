"""Speech-to-Text abstraction and engines subpackage."""

from taskify.stt.base import STTEngine
from taskify.stt.download import (
    VOSK_MODEL_URLS,
    download_vosk_model,
    download_whisper_model,
)
from taskify.stt.factory import get_stt_engine
from taskify.stt.vosk_engine import VoskEngine
from taskify.stt.whisper_engine import WhisperEngine

__all__ = [
    "STTEngine",
    "VoskEngine",
    "WhisperEngine",
    "get_stt_engine",
    "download_vosk_model",
    "download_whisper_model",
    "VOSK_MODEL_URLS",
]
