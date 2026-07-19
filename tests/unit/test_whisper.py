"""Unit tests for Whisper speech-to-text engine and configurations."""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    StorageSettings,
    STTSettings,
)
from taskify.stt import WhisperEngine, download_whisper_model, get_stt_engine


@pytest.fixture
def dummy_settings() -> Settings:
    """Fixture returning dummy settings for Whisper testing."""
    return Settings(
        audio=AudioSettings(
            device="default",
            sample_rate=16000,
            chunk_duration_ms=200,
            silence_threshold=0.01,
            silence_duration_s=1.5,
        ),
        stt=STTSettings(
            engine="whisper",
            vosk_model="en-small",
            whisper_model="tiny",
            language="en",
        ),
        llm=LLMSettings(
            backend="nlp",
            ollama_host="http://localhost:11434",
            ollama_model="phi4",
            extraction_interval_s=300,
        ),
        storage=StorageSettings(data_dir=None, log_dir=None),  # type: ignore
        logging=LoggingSettings(level="INFO", debug_llm=False),
    )


@pytest.fixture
def mock_faster_whisper_module() -> ModuleType:
    """Inject a fake faster_whisper module into sys.modules so lazy import succeeds."""
    fake_module = ModuleType("faster_whisper")

    # Create a mock WhisperModel class that will be returned by the fake module
    mock_model_instance = MagicMock()
    mock_seg_1 = MagicMock()
    mock_seg_1.text = "Write a quick task"
    mock_seg_2 = MagicMock()
    mock_seg_2.text = "for Antigravity."
    mock_model_instance.transcribe.return_value = ([mock_seg_1, mock_seg_2], None)

    mock_model_class = MagicMock(return_value=mock_model_instance)
    fake_module.WhisperModel = mock_model_class  # type: ignore[attr-defined]

    # Inject into sys.modules so 'from faster_whisper import WhisperModel' resolves
    sys.modules["faster_whisper"] = fake_module
    yield fake_module
    # Clean up after test
    sys.modules.pop("faster_whisper", None)


def test_whisper_factory_resolution(dummy_settings: Settings) -> None:
    """Test that STT factory instantiates WhisperEngine under settings."""
    engine = get_stt_engine(dummy_settings)
    assert isinstance(engine, WhisperEngine)
    assert engine._model_size == "tiny"
    assert engine._language == "en"


def test_whisper_lazy_import_not_installed(dummy_settings: Settings) -> None:
    """Test that initialization raises ImportError when faster-whisper is missing."""
    engine = WhisperEngine(dummy_settings)
    # Ensure faster_whisper is NOT in sys.modules for this test
    sys.modules.pop("faster_whisper", None)

    with patch.dict("sys.modules", {"faster_whisper": None}):  # type: ignore[dict-item]
        with pytest.raises((ImportError, ModuleNotFoundError)):
            engine.initialize()


def test_whisper_transcription_and_flush(
    dummy_settings: Settings,
    mock_faster_whisper_module: ModuleType,
) -> None:
    """Test that WhisperEngine accumulates chunks and processes batch on flush."""
    engine = WhisperEngine(dummy_settings)
    engine.initialize()
    assert engine.is_initialized()

    # transcribe_chunk should return None and accumulate
    chunk_1 = np.ones(3200, dtype=np.float32) * 0.1
    chunk_2 = np.ones(3200, dtype=np.float32) * 0.2

    assert engine.transcribe_chunk(chunk_1) is None
    assert engine.transcribe_chunk(chunk_2) is None
    assert len(engine._audio_buffer) == 2

    # flush should process concatenated segments and clear buffer
    final_text = engine.flush()
    assert final_text == "Write a quick task for Antigravity."
    assert len(engine._audio_buffer) == 0

    # Verify model.transcribe was called with concatenated audio (6400 frames)
    mock_model_instance = mock_faster_whisper_module.WhisperModel.return_value
    mock_model_instance.transcribe.assert_called_once()
    args, _ = mock_model_instance.transcribe.call_args
    assert isinstance(args[0], np.ndarray)
    assert len(args[0]) == 6400


def test_download_whisper_model_invalid_size() -> None:
    """Test that Whisper downloader raises ValueError on invalid size name."""
    with pytest.raises(ValueError, match="is not supported"):
        download_whisper_model("large-model-custom")
