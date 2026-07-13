"""Unit tests for microphone audio capture and silence detection."""

import collections
import queue
from typing import Generator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from taskify.audio import AudioCapture
from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    STTSettings,
    StorageSettings,
)


@pytest.fixture
def dummy_settings() -> Settings:
    """Fixture returning dummy settings for capture testing."""
    return Settings(
        audio=AudioSettings(
            device="default",
            sample_rate=16000,
            chunk_duration_ms=200,
            silence_threshold=0.05,
            silence_duration_s=0.6,  # 0.6s at 200ms = 3 chunks limit
        ),
        stt=STTSettings(
            engine="vosk", vosk_model="en-small", whisper_model="base", language="en"
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


@patch("sounddevice.query_devices")
def test_get_available_devices(mock_query: MagicMock) -> None:
    """Test that available devices are queried and filtered correctly."""
    mock_query.return_value = [
        {"name": "Mute Mic", "max_input_channels": 0, "default_samplerate": 44100.0},
        {"name": "Real Mic", "max_input_channels": 2, "default_samplerate": 16000.0},
    ]

    devices = AudioCapture.get_available_devices()
    assert len(devices) == 1
    assert devices[0]["name"] == "Real Mic"
    assert devices[0]["max_input_channels"] == 2


def test_resolve_device_index(dummy_settings: Settings) -> None:
    """Test resolving configuration device name to PortAudio device identifiers."""
    # Default device configuration
    capture = AudioCapture(dummy_settings)
    assert capture._resolve_device_index() is None

    # Index device configuration
    dummy_settings.audio.device = "3"
    capture = AudioCapture(dummy_settings)
    assert capture._resolve_device_index() == 3

    # Named device configuration
    with patch("sounddevice.query_devices") as mock_query:
        mock_query.return_value = [
            {"name": "Primary Microphone", "max_input_channels": 1},
            {"name": "Virtual Audio Cable", "max_input_channels": 2},
        ]
        dummy_settings.audio.device = "Cable"
        capture = AudioCapture(dummy_settings)
        assert capture._resolve_device_index() == 1

        # Unknown device
        dummy_settings.audio.device = "UnknownDevice"
        capture = AudioCapture(dummy_settings)
        assert capture._resolve_device_index() is None


def test_silence_detection_state_transitions(dummy_settings: Settings) -> None:
    """Test state machine transitions between SILENT and ACTIVE states."""
    capture = AudioCapture(dummy_settings)

    # State parameters:
    # Threshold = 0.05
    # Silence limit = 3 chunks (0.6s)
    # Pre-roll maxlen = 3 chunks (600ms)

    # 1. Create mock audio frames
    silent_frame = np.zeros((3200, 1), dtype=np.float32)  # RMS = 0.0
    active_frame = np.ones((3200, 1), dtype=np.float32) * 0.1  # RMS = 0.1 > 0.05

    # Initially in SILENT state
    assert capture._state == 0
    assert len(capture._preroll_buffer) == 0

    # 2. Feed a silent frame -> Should add to pre-roll, not queue
    capture._audio_callback(silent_frame, 3200, None, None)
    assert capture._state == 0
    assert len(capture._preroll_buffer) == 1
    assert capture._queue.empty()

    # Feed two more silent frames -> Pre-roll full (3 frames)
    capture._audio_callback(silent_frame, 3200, None, None)
    capture._audio_callback(silent_frame, 3200, None, None)
    assert len(capture._preroll_buffer) == 3
    assert capture._queue.empty()

    # Feed a fourth silent frame -> Pre-roll remains at maxlen 3
    capture._audio_callback(silent_frame, 3200, None, None)
    assert len(capture._preroll_buffer) == 3
    assert capture._queue.empty()

    # 3. Feed active frame -> Transitions to ACTIVE (1)
    # Queues pre-roll frames (3) + current active frame (1) = 4 items in queue
    capture._audio_callback(active_frame, 3200, None, None)
    assert capture._state == 1
    assert capture._silence_counter == 0
    assert capture._queue.qsize() == 4
    assert len(capture._preroll_buffer) == 0

    # Feed another active frame -> Queue size = 5, stays ACTIVE
    capture._audio_callback(active_frame, 3200, None, None)
    assert capture._state == 1
    assert capture._queue.qsize() == 5

    # 4. Feed a silent frame while active -> Queue size = 6, stays active, increment counter
    capture._audio_callback(silent_frame, 3200, None, None)
    assert capture._state == 1
    assert capture._silence_counter == 1
    assert capture._queue.qsize() == 6

    # Feed second silent frame -> Queue size = 7, stays active, increment counter
    capture._audio_callback(silent_frame, 3200, None, None)
    assert capture._state == 1
    assert capture._silence_counter == 2
    assert capture._queue.qsize() == 7

    # Feed third silent frame -> Hits silence limit (3), transitions to SILENT (0)
    # Does not queue current frame. Sets it as first pre-roll frame instead.
    capture._audio_callback(silent_frame, 3200, None, None)
    assert capture._state == 0
    assert capture._silence_counter == 0
    assert capture._queue.qsize() == 7  # stays at 7
    assert len(capture._preroll_buffer) == 1
