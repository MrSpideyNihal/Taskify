"""Unit tests for the MainWindow GUI dashboard component using a mock GUI module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# Create dummy classes to prevent Tkinter window rendering or unittest.mock spec conflicts
class CTkDummy:
    def __init__(self, *args, **kwargs) -> None:
        pass
    def title(self, *args, **kwargs) -> None:
        pass
    def geometry(self, *args, **kwargs) -> None:
        pass
    def minsize(self, *args, **kwargs) -> None:
        pass
    def configure(self, *args, **kwargs) -> None:
        pass
    def grid_rowconfigure(self, *args, **kwargs) -> None:
        pass
    def grid_columnconfigure(self, *args, **kwargs) -> None:
        pass
    def after(self, *args, **kwargs) -> None:
        pass
    def destroy(self, *args, **kwargs) -> None:
        pass

class CTkFrameDummy:
    def __init__(self, *args, **kwargs) -> None:
        pass
    def grid(self, *args, **kwargs) -> None:
        pass
    def pack(self, *args, **kwargs) -> None:
        pass
    def configure(self, *args, **kwargs) -> None:
        pass
    def bind(self, *args, **kwargs) -> None:
        pass
    def winfo_children(self) -> list:
        return []
    def grid_rowconfigure(self, *args, **kwargs) -> None:
        pass
    def grid_columnconfigure(self, *args, **kwargs) -> None:
        pass

class CTkLabelDummy:
    def __init__(self, *args, **kwargs) -> None:
        pass
    def grid(self, *args, **kwargs) -> None:
        pass
    def pack(self, *args, **kwargs) -> None:
        pass
    def configure(self, *args, **kwargs) -> None:
        pass
    def bind(self, *args, **kwargs) -> None:
        pass

class CTkScrollableFrameDummy:
    def __init__(self, *args, **kwargs) -> None:
        pass
    def grid(self, *args, **kwargs) -> None:
        pass
    def bind(self, *args, **kwargs) -> None:
        pass
    def winfo_children(self) -> list:
        return []
    def grid_columnconfigure(self, *args, **kwargs) -> None:
        pass

class CTkFontDummy:
    def __init__(self, *args, **kwargs) -> None:
        pass

# Mock the entire customtkinter module before any imports of main_window
mock_ctk = MagicMock()
mock_ctk.CTk = CTkDummy
mock_ctk.CTkFrame = CTkFrameDummy
mock_ctk.CTkLabel = CTkLabelDummy
mock_ctk.CTkScrollableFrame = CTkScrollableFrameDummy
mock_ctk.CTkFont = CTkFontDummy
mock_ctk.set_appearance_mode = MagicMock()
mock_ctk.set_default_color_theme = MagicMock()

sys.modules["customtkinter"] = mock_ctk

import pytest

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    STTSettings,
    StorageSettings,
)
from taskify.llm.models import MatrixQuadrant
from taskify.pipeline.scheduler import EVENT_TASKS_UPDATED, EventBus
from taskify.storage.models import MatrixEntry, TaskRecord
from taskify.ui.main_window import MainWindow


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
        storage=StorageSettings(data_dir=None, log_dir=None),  # type: ignore
        logging=LoggingSettings(level="INFO", debug_llm=False),
    )


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    task = TaskRecord(
        id=42,
        title="Test Task Title",
        notes="Test Notes",
        due_date="2026-07-20",
        status="pending",
        created_at="2026-07-17 12:00:00",
    )
    matrix = MatrixEntry(task_id=42, quadrant="do_first")
    db.get_tasks_in_quadrant.return_value = [(task, matrix)]
    db.get_task.return_value = (task, matrix)
    return db


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def test_main_window_initialization(
    mock_db: MagicMock,
    dummy_settings: Settings,
    bus: EventBus,
) -> None:
    """Test that MainWindow configures parameters and registers event listener."""
    window = MainWindow(mock_db, dummy_settings, bus)
    
    # Assert that quadrants are present in window
    assert len(window.quadrants) == 4
    assert MatrixQuadrant.DO_FIRST.value in window.quadrants


def test_refresh_all_quadrants(
    mock_db: MagicMock,
    dummy_settings: Settings,
    bus: EventBus,
) -> None:
    """Test that refresh_all_quadrants queries database and recreates task cards."""
    mock_scroll_instance = MagicMock()
    mock_scroll_instance.winfo_children.return_value = []

    window = MainWindow(mock_db, dummy_settings, bus)

    # Force mock scrollable frame instances inside quadrants dict
    for q_key in window.quadrants:
        window.quadrants[q_key] = mock_scroll_instance

    # Reset mock call count from initial instantiation
    mock_db.get_tasks_in_quadrant.reset_mock()

    with patch("taskify.ui.main_window.TaskCard") as mock_task_card_class:
        window.refresh_all_quadrants()
        
        # Verify db.get_tasks_in_quadrant was called for each quadrant
        assert mock_db.get_tasks_in_quadrant.call_count == 4
        # Verify TaskCard was instantiated
        assert mock_task_card_class.call_count > 0


def test_handle_task_action_complete(
    mock_db: MagicMock,
    dummy_settings: Settings,
    bus: EventBus,
) -> None:
    """Test task completion action invokes db.update_task with 'completed'."""
    window = MainWindow(mock_db, dummy_settings, bus)

    window.handle_task_action("complete", 42)
    
    mock_db.get_task.assert_called_once_with(42)
    mock_db.update_task.assert_called_once_with(
        task_id=42,
        title="Test Task Title",
        notes="Test Notes",
        due_date="2026-07-20",
        status="completed",
    )


def test_handle_task_action_delete(
    mock_db: MagicMock,
    dummy_settings: Settings,
    bus: EventBus,
) -> None:
    """Test task deletion action invokes db.delete_task."""
    window = MainWindow(mock_db, dummy_settings, bus)

    window.handle_task_action("delete", 42)
    
    mock_db.delete_task.assert_called_once_with(42)


def test_handle_task_action_move(
    mock_db: MagicMock,
    dummy_settings: Settings,
    bus: EventBus,
) -> None:
    """Test moving quadrant action invokes db.override_matrix_quadrant."""
    window = MainWindow(mock_db, dummy_settings, bus)

    window.handle_task_action("move_schedule", 42)
    
    mock_db.override_matrix_quadrant.assert_called_once_with(42, "schedule")


def test_event_bus_refreshes_ui(
    mock_db: MagicMock,
    dummy_settings: Settings,
    bus: EventBus,
) -> None:
    """Test that emitting EVENT_TASKS_UPDATED schedules UI refresh."""
    window = MainWindow(mock_db, dummy_settings, bus)
    
    with patch.object(window, "after") as mock_after:
        bus.emit(EVENT_TASKS_UPDATED)
        
        # event should trigger UI schedule via window.after
        assert mock_after.call_count >= 1
