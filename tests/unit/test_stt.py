"""Unit tests for speech-to-text engines, factory, and download utilities."""

from pathlib import Path
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
from taskify.stt import (
    VoskEngine,
    download_vosk_model,
    get_stt_engine,
)


@pytest.fixture
def dummy_settings() -> Settings:
    """Fixture returning dummy settings for STT testing."""
    return Settings(
        audio=AudioSettings(
            device="default",
            sample_rate=16000,
            chunk_duration_ms=200,
            silence_threshold=0.01,
            silence_duration_s=1.5,
        ),
        stt=STTSettings(
            engine="vosk",
            vosk_model="en-small",
            whisper_model="base",
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


def test_stt_engine_factory(dummy_settings: Settings) -> None:
    """Test STT factory engine resolution logic."""
    # Test vosk
    engine = get_stt_engine(dummy_settings)
    assert isinstance(engine, VoskEngine)

    # Test whisper now returns WhisperEngine
    from taskify.stt import WhisperEngine

    dummy_settings.stt.engine = "whisper"
    whisper_engine = get_stt_engine(dummy_settings)
    assert isinstance(whisper_engine, WhisperEngine)

    # Test unknown engine selection
    dummy_settings.stt.engine = "unsupported"
    with pytest.raises(ValueError, match="Unknown speech-to-text engine"):
        get_stt_engine(dummy_settings)


@patch("sounddevice.query_devices")
def test_vosk_engine_initialization_failure(
    mock_sd: MagicMock, dummy_settings: Settings, tmp_path: Path
) -> None:
    """Test VoskEngine initialization fails if model directory does not exist."""
    # Point models root to temporary path where model does not exist
    engine = VoskEngine(dummy_settings)
    engine._model_root = tmp_path

    with pytest.raises(RuntimeError, match="Vosk model not found"):
        engine.initialize()


@patch("vosk.Model")
@patch("vosk.KaldiRecognizer")
def test_vosk_engine_transcription(
    mock_rec_class: MagicMock,
    mock_model_class: MagicMock,
    dummy_settings: Settings,
    tmp_path: Path,
) -> None:
    """Test VoskEngine transcription conversions and result processing."""
    # Build fake model directory
    model_dir = tmp_path / "vosk-model-small-en-us-0.15"
    model_dir.mkdir()

    engine = VoskEngine(dummy_settings)
    engine._model_root = tmp_path

    # Mock Vosk recognizer instance
    mock_rec = MagicMock()
    mock_rec.AcceptWaveform.return_value = True
    mock_rec.Result.return_value = '{"text": "hello taskify team"}'
    mock_rec.FinalResult.return_value = '{"text": "final phrase text"}'
    mock_rec_class.return_value = mock_rec

    # Initialize
    engine.initialize()
    assert engine.is_initialized()

    # Transcribe Chunk
    chunk = np.zeros(3200, dtype=np.float32)
    text = engine.transcribe_chunk(chunk)
    assert text == "hello taskify team"

    # Audio data mapping checks: AcceptWaveform was called with bytes
    mock_rec.AcceptWaveform.assert_called_once()
    args, _ = mock_rec.AcceptWaveform.call_args
    assert isinstance(args[0], bytes)
    # 3200 float32 points * 2 bytes/int16 = 6400 bytes
    assert len(args[0]) == 6400

    # Flush final transcription
    final_text = engine.flush()
    assert final_text == "final phrase text"


def test_download_vosk_model_invalid_name() -> None:
    """Test that download utility throws ValueError on unknown models."""
    with pytest.raises(ValueError, match="is not in the supported catalog"):
        download_vosk_model("invalid-model-name")
