"""Unit tests for the SettingsDialog GUI configuration component."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    StorageSettings,
    STTSettings,
)
from taskify.ui.settings_dialog import SettingsDialog


@pytest.fixture
def mock_parent() -> MagicMock:
    parent = MagicMock()
    parent._bus = MagicMock()
    return parent


@pytest.fixture
def dummy_settings() -> Settings:
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
        storage=StorageSettings(
            data_dir=Path("/dummy/data"),
            log_dir=Path("/dummy/log"),
        ),
        logging=LoggingSettings(
            level="INFO",
            debug_llm=False,
        ),
    )


@pytest.fixture
def dialog(mock_parent, dummy_settings) -> SettingsDialog:
    return SettingsDialog(mock_parent, dummy_settings)


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestSettingsDialogInit:
    def test_default_values_load(self, dialog: SettingsDialog) -> None:
        assert dialog.device_var.get() == "default"
        assert dialog.sample_rate_var.get() == "16000"
        assert dialog.chunk_duration_var.get() == "200"
        assert dialog.stt_engine_var.get() == "vosk"
        assert dialog.vosk_model_var.get() == "en-small"
        assert dialog.whisper_model_var.get() == "base"
        assert dialog.language_var.get() == "en"
        assert dialog.llm_backend_var.get() == "nlp"
        assert dialog.ollama_host_var.get() == "http://localhost:11434"
        assert dialog.ollama_model_var.get() == "phi4"
        assert dialog.interval_var.get() == "300"
        assert dialog.log_level_var.get() == "INFO"
        assert dialog.debug_llm_var.get() is False


# ---------------------------------------------------------------------------
# UI Interactions
# ---------------------------------------------------------------------------


class TestSettingsDialogUIInteractions:
    def test_stt_engine_changed(self, dialog: SettingsDialog) -> None:
        # Check no crash when choosing whisper
        dialog._on_stt_engine_changed("whisper")
        # Check no crash when choosing vosk
        dialog._on_stt_engine_changed("vosk")

    def test_llm_backend_changed(self, dialog: SettingsDialog) -> None:
        # Check no crash when choosing ollama
        dialog._on_llm_backend_changed("ollama")
        # Check no crash when choosing nlp
        dialog._on_llm_backend_changed("nlp")

    def test_browse_data_dir(self, dialog: SettingsDialog) -> None:
        with patch("tkinter.filedialog.askdirectory", return_value="/new/data/dir"):
            dialog._browse_data_dir()
        assert dialog.data_dir_var.get() == "/new/data/dir"

    def test_browse_log_dir(self, dialog: SettingsDialog) -> None:
        with patch("tkinter.filedialog.askdirectory", return_value="/new/log/dir"):
            dialog._browse_log_dir()
        assert dialog.log_dir_var.get() == "/new/log/dir"


# ---------------------------------------------------------------------------
# Validation & Saving tests
# ---------------------------------------------------------------------------


class TestSettingsDialogSaveValidation:
    def test_save_valid_vosk_settings(self, dialog: SettingsDialog) -> None:
        with (
            patch.dict(sys.modules, {"vosk": MagicMock()}),
            patch(
                "taskify.stt.vosk_engine.VoskEngine.model_path",
                new_callable=PropertyMock,
            ) as mock_path,
            patch("taskify.ui.settings_dialog.save_settings") as mock_save,
        ):
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_dir.is_dir.return_value = True
            mock_path.return_value = mock_dir

            dialog.save()

            assert mock_save.called
            assert dialog.parent.apply_settings.called

    def test_save_invalid_audio_numbers(self, dialog: SettingsDialog) -> None:
        dialog.sample_rate_var.set("invalid_rate")
        with patch("tkinter.messagebox.showerror") as mock_err:
            dialog.save()
            assert mock_err.called
            assert (
                "Invalid format in Audio numeric values"
                in mock_err.call_args[1]["message"]
            )

    def test_save_negative_audio_rate(self, dialog: SettingsDialog) -> None:
        dialog.sample_rate_var.set("-16000")
        with patch("tkinter.messagebox.showerror") as mock_err:
            dialog.save()
            assert mock_err.called
            assert (
                "audio.sample_rate must be a positive integer"
                in mock_err.call_args[1]["message"]
            )

    def test_save_whisper_checks_installed(self, dialog: SettingsDialog) -> None:
        dialog.stt_engine_var.set("whisper")
        dialog.whisper_model_var.set("base")

        # Mock faster_whisper import failure
        with patch.dict(sys.modules, {"faster_whisper": None}):
            with patch("tkinter.messagebox.showerror") as mock_err:
                dialog.save()
                assert mock_err.called
                assert (
                    "faster-whisper' is not installed"
                    in mock_err.call_args[1]["message"]
                )

    def test_save_whisper_invalid_model(self, dialog: SettingsDialog) -> None:
        dialog.stt_engine_var.set("whisper")
        dialog.whisper_model_var.set("nonexistent_model")

        # Mock faster-whisper is installed
        with patch.dict(sys.modules, {"faster_whisper": MagicMock()}):
            with patch("tkinter.messagebox.showerror") as mock_err:
                dialog.save()
                assert mock_err.called
                assert (
                    "invalid, and no such local model folder exists"
                    in mock_err.call_args[1]["message"]
                )

    def test_save_vosk_checks_installed(self, dialog: SettingsDialog) -> None:
        dialog.stt_engine_var.set("vosk")

        # Mock vosk import failure
        with patch.dict(sys.modules, {"vosk": None}):
            with patch("tkinter.messagebox.showerror") as mock_err:
                dialog.save()
                assert mock_err.called
                assert (
                    "vosk' package is not installed" in mock_err.call_args[1]["message"]
                )

    def test_save_vosk_missing_model_path(self, dialog: SettingsDialog) -> None:
        dialog.stt_engine_var.set("vosk")
        dialog.vosk_model_var.set("en-small")

        with patch.dict(sys.modules, {"vosk": MagicMock()}):
            with patch(
                "taskify.stt.vosk_engine.VoskEngine.model_path",
                new_callable=PropertyMock,
            ) as mock_path:
                mock_dir = MagicMock()
                mock_dir.exists.return_value = False  # Model path doesn't exist
                mock_path.return_value = mock_dir

                with patch("tkinter.messagebox.showerror") as mock_err:
                    dialog.save()
                    assert mock_err.called
                    assert "not found locally at" in mock_err.call_args[1]["message"]

    def test_save_invalid_interval(self, dialog: SettingsDialog) -> None:
        dialog.interval_var.set("invalid_interval")

        # Mock vosk dependency and model directory checks so STT validation passes
        with patch.dict(sys.modules, {"vosk": MagicMock()}):
            with patch(
                "taskify.stt.vosk_engine.VoskEngine.model_path",
                new_callable=PropertyMock,
            ) as mock_path:
                mock_dir = MagicMock()
                mock_dir.exists.return_value = True
                mock_dir.is_dir.return_value = True
                mock_path.return_value = mock_dir

                with patch("tkinter.messagebox.showerror") as mock_err:
                    dialog.save()
                    assert mock_err.called
                    assert (
                        "Extraction interval must be an integer"
                        in mock_err.call_args[1]["message"]
                    )
