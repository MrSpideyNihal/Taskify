"""Unit tests for structured logging configuration and custom session filtering."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    StorageSettings,
    STTSettings,
)
from taskify.logging_config import (
    SessionIDFilter,
    configure_logging,
    set_active_session_id,
)


@pytest.fixture
def dummy_settings(tmp_path: Path) -> Settings:
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
            backend="ollama",
            ollama_host="http://localhost:11434",
            ollama_model="phi4-mini",
            extraction_interval_s=300,
        ),
        storage=StorageSettings(
            data_dir=tmp_path / "data",
            log_dir=tmp_path / "logs",
        ),
        logging=LoggingSettings(
            level="DEBUG",
            debug_llm=True,
        ),
    )


def test_session_id_filter_defaults_to_na() -> None:
    # Ensure default session ID is N/A
    set_active_session_id(None)
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test_path.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    filtr = SessionIDFilter()
    assert filtr.filter(record)
    assert record.session_id == "N/A"


def test_session_id_filter_updates_via_set_active() -> None:
    # Set explicit session ID and check record updates
    set_active_session_id("uuid-1234-5678")
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test_path.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    filtr = SessionIDFilter()
    assert filtr.filter(record)
    assert record.session_id == "uuid-1234-5678"

    # Reset
    set_active_session_id(None)
    filtr.filter(record)
    assert record.session_id == "N/A"


def test_configure_logging_creates_handlers(dummy_settings: Settings) -> None:
    configure_logging(dummy_settings)

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) >= 2

    # Check that console and rotating file handlers are added
    handlers = root_logger.handlers
    has_console = any(isinstance(h, logging.StreamHandler) for h in handlers)
    has_file = any(isinstance(h, RotatingFileHandler) for h in handlers)

    assert has_console
    assert has_file

    # Clean up handlers to prevent side effects in other tests
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)


def test_rotating_file_handler_rotation(tmp_path: Path) -> None:
    # Set up small rotation log to verify rotation on write threshold
    log_file = tmp_path / "test_rotation.log"
    handler = RotatingFileHandler(
        log_file,
        maxBytes=100,  # Tiny limit to force immediate rotation
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("test_rotator")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Write logs exceeding 100 bytes
    logger.info("A" * 60)
    logger.info("B" * 60)
    logger.info("C" * 60)

    handler.close()
    logger.removeHandler(handler)

    # Check that backup rotation files were generated
    assert log_file.exists()
    assert (tmp_path / "test_rotation.log.1").exists()
