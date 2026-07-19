"""Unit tests for the Taskify configuration management and settings."""

from pathlib import Path

import pytest

from taskify.config import (
    get_default_paths,
    load_settings,
)
from taskify.config.settings import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    STTSettings,
    merge_dicts,
)


def test_get_default_paths() -> None:
    """Test that default paths are computed correctly and are pathlib Paths."""
    config_dir, data_dir = get_default_paths()
    assert isinstance(config_dir, Path)
    assert isinstance(data_dir, Path)
    assert config_dir.name.lower() == "taskify"
    assert data_dir.name.lower() == "taskify"


def test_merge_dicts() -> None:
    """Test recursive dictionary merging."""
    default = {
        "audio": {"device": "default", "sample_rate": 16000},
        "logging": {"level": "INFO"},
    }
    override = {"audio": {"sample_rate": 22050}, "logging": {"level": "DEBUG"}}
    merged = merge_dicts(default, override)

    assert merged["audio"]["device"] == "default"
    assert merged["audio"]["sample_rate"] == 22050
    assert merged["logging"]["level"] == "DEBUG"


def test_load_default_settings(tmp_path: Path) -> None:
    """Test that settings load defaults correctly when no override file exists."""
    # Point user configuration to a non-existent temporary file
    temp_config_path = tmp_path / "non_existent_config.toml"
    settings = load_settings(user_config_path=temp_config_path)

    assert settings.config_path is None
    assert settings.audio.sample_rate == 16000
    assert settings.stt.engine == "vosk"
    assert settings.llm.backend == "ollama"
    assert settings.logging.level == "INFO"


def test_load_override_settings(tmp_path: Path) -> None:
    """Test that settings load correct values with a custom override file."""
    temp_config_path = tmp_path / "config.toml"
    temp_config_path.write_text(
        "[audio]\nsample_rate = 44100\n\n[logging]\nlevel = 'DEBUG'",
        encoding="utf-8",
    )

    settings = load_settings(user_config_path=temp_config_path)
    assert settings.config_path == temp_config_path
    assert settings.audio.sample_rate == 44100
    assert settings.audio.device == "default"  # check fallthrough default
    assert settings.logging.level == "DEBUG"


def test_settings_validation_errors() -> None:
    """Test that invalid configuration parameters raise validation exceptions."""
    # Invalid audio sample rate
    with pytest.raises(ValueError, match="audio.sample_rate"):
        AudioSettings(
            device="default",
            sample_rate=0,
            chunk_duration_ms=200,
            silence_threshold=0.01,
            silence_duration_s=1.5,
        ).validate()

    # Invalid audio silence threshold
    with pytest.raises(ValueError, match="audio.silence_threshold"):
        AudioSettings(
            device="default",
            sample_rate=16000,
            chunk_duration_ms=200,
            silence_threshold=-0.1,
            silence_duration_s=1.5,
        ).validate()

    # Invalid STT engine selection
    with pytest.raises(ValueError, match="stt.engine"):
        STTSettings(
            engine="invalid_engine",
            vosk_model="en-small",
            whisper_model="base",
            language="en",
        ).validate()

    # Invalid LLM backend selection
    with pytest.raises(ValueError, match="llm.backend"):
        LLMSettings(
            backend="openai",
            ollama_host="localhost",
            ollama_model="phi4",
            extraction_interval_s=300,
        ).validate()

    # Invalid logging level choice
    with pytest.raises(ValueError, match="logging.level"):
        LoggingSettings(level="TRACE", debug_llm=False).validate()
