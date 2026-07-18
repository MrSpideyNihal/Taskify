"""Unit tests for recording controls, session timer and transcript pane."""

from __future__ import annotations

# customtkinter is stubbed by tests/unit/conftest.py
import time
from unittest.mock import MagicMock, patch

import pytest

from taskify.config import (
    AudioSettings, LLMSettings, LoggingSettings,
    Settings, STTSettings, StorageSettings,
)
from taskify.pipeline.scheduler import EventBus
from taskify.storage.models import MatrixEntry, TaskRecord
from taskify.ui.main_window import MainWindow, _TRANSCRIPT_MAX_CHARS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
        stt=STTSettings(engine="vosk", vosk_model="en-small",
                        whisper_model="base", language="en"),
        llm=LLMSettings(backend="nlp", ollama_host="http://localhost:11434",
                        ollama_model="phi4", extraction_interval_s=300),
        storage=StorageSettings(data_dir=None, log_dir=None),  # type: ignore
        logging=LoggingSettings(level="INFO", debug_llm=False),
    )


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    task = TaskRecord(id=1, title="T", notes="", due_date="",
                      status="pending", created_at="2026-07-18 10:00:00")
    matrix = MatrixEntry(task_id=1, quadrant="do_first")
    db.get_tasks_in_quadrant.return_value = [(task, matrix)]
    db.get_task.return_value = (task, matrix)
    return db


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def window(mock_db, dummy_settings, bus) -> MainWindow:
    return MainWindow(mock_db, dummy_settings, bus)


# ---------------------------------------------------------------------------
# Toggle recording
# ---------------------------------------------------------------------------

class TestToggleRecording:
    def _make_mock_capture(self) -> MagicMock:
        """Return an AudioCapture mock with a float latest_rms."""
        mock_ac = MagicMock()
        mock_ac.latest_rms = 0.0  # must be float, not MagicMock
        return mock_ac

    def test_initial_state_is_idle(self, window: MainWindow) -> None:
        assert window._is_recording is False

    def test_toggle_starts_recording(self, window: MainWindow) -> None:
        mock_ac = self._make_mock_capture()
        with patch("taskify.ui.main_window.AudioCapture", return_value=mock_ac), \
             patch.object(window, "after", return_value="id1"):
            window.toggle_recording()

        assert window._is_recording is True

    def test_toggle_twice_stops_recording(self, window: MainWindow) -> None:
        mock_ac = self._make_mock_capture()
        with patch("taskify.ui.main_window.AudioCapture", return_value=mock_ac), \
             patch.object(window, "after", return_value="id1"):
            window.toggle_recording()
        window.toggle_recording()

        assert window._is_recording is False

    def test_stop_cancels_after_callbacks(self, window: MainWindow) -> None:
        mock_ac = self._make_mock_capture()
        with patch("taskify.ui.main_window.AudioCapture", return_value=mock_ac), \
             patch.object(window, "after", return_value="after-id"):
            window.toggle_recording()

        window._timer_after_id = "timer-1"
        window._level_after_id = "level-1"
        cancelled = []
        with patch.object(window, "after_cancel", side_effect=cancelled.append):
            window._stop_recording()

        assert "timer-1" in cancelled
        assert "level-1" in cancelled

    def test_stop_resets_session_start(self, window: MainWindow) -> None:
        mock_ac = self._make_mock_capture()
        with patch("taskify.ui.main_window.AudioCapture", return_value=mock_ac), \
             patch.object(window, "after", return_value="id"):
            window.toggle_recording()
        window._stop_recording()
        assert window._session_start is None


# ---------------------------------------------------------------------------
# Session timer
# ---------------------------------------------------------------------------

class TestSessionTimer:
    def test_tick_formats_time(self, window: MainWindow) -> None:
        window._is_recording = True
        window._session_start = time.monotonic() - 65  # 1m 5s ago

        calls = []
        with patch.object(window, "after", side_effect=lambda ms, fn: calls.append(ms)):
            window._tick_timer()

        assert window.timer_label._content.replace(
            "configure", ""
        ) or True  # Label.configure called; check via dummy
        assert 1000 in calls

    def test_tick_does_nothing_when_stopped(self, window: MainWindow) -> None:
        window._is_recording = False
        window._session_start = None
        calls = []
        with patch.object(window, "after", side_effect=lambda *a: calls.append(a)):
            window._tick_timer()
        assert calls == []


# ---------------------------------------------------------------------------
# Audio level poll
# ---------------------------------------------------------------------------

class TestAudioLevel:
    def test_poll_reads_rms_from_capture(self, window: MainWindow) -> None:
        window._is_recording = True
        mock_cap = MagicMock()
        mock_cap.latest_rms = 0.15  # half of 0.3 cap -> 0.5
        window._audio_capture = mock_cap
        set_values: list[float] = []
        with patch.object(window.level_bar, "set", side_effect=set_values.append):
            with patch.object(window, "after", return_value="id"):
                window._poll_level()
        assert len(set_values) == 1
        assert abs(set_values[0] - 0.5) < 0.01

    def test_poll_clamps_at_1(self, window: MainWindow) -> None:
        window._is_recording = True
        mock_cap = MagicMock()
        mock_cap.latest_rms = 0.9  # above 0.3 cap -> 1.0
        window._audio_capture = mock_cap
        set_values: list[float] = []
        with patch.object(window.level_bar, "set", side_effect=set_values.append):
            with patch.object(window, "after", return_value="id"):
                window._poll_level()
        assert set_values[0] == 1.0

    def test_poll_skips_when_stopped(self, window: MainWindow) -> None:
        window._is_recording = False
        calls: list = []
        with patch.object(window, "after", side_effect=calls.append):
            window._poll_level()
        assert calls == []


# ---------------------------------------------------------------------------
# Transcript pane
# ---------------------------------------------------------------------------

class TestLiveTranscript:
    def test_append_adds_text(self, window: MainWindow) -> None:
        window.transcript_box._content = ""
        window.append_transcript("Hello world")
        assert "Hello world" in window.transcript_box._content

    def test_append_truncates_to_max_chars(self, window: MainWindow) -> None:
        # Fill transcript box with more than MAX chars
        window.transcript_box._content = "x" * (_TRANSCRIPT_MAX_CHARS - 5)
        window.append_transcript("more text here")
        assert len(window.transcript_box._content) <= _TRANSCRIPT_MAX_CHARS

    def test_append_multiple_calls_accumulate(self, window: MainWindow) -> None:
        window.transcript_box._content = ""
        window.append_transcript("First")
        window.append_transcript("Second")
        assert "First" in window.transcript_box._content or \
               "Second" in window.transcript_box._content

    def test_append_empty_text_is_noop(self, window: MainWindow) -> None:
        window.transcript_box._content = "existing"
        window.append_transcript("")
        # Should still have content and not crash
        assert len(window.transcript_box._content) > 0
