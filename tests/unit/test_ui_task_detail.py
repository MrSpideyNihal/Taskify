"""Unit tests for the TaskDetailPanel sidebar configuration component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from taskify.storage.database import DatabaseManager
from taskify.storage.models import TaskRecord
from taskify.ui.main_window import TaskCard
from taskify.ui.task_detail_panel import TaskDetailPanel


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def db_manager(temp_db_path: Path) -> DatabaseManager:
    db = DatabaseManager(temp_db_path)
    yield db
    db.close()


@pytest.fixture
def mock_parent() -> MagicMock:
    parent = MagicMock()
    parent.refresh_all_quadrants = MagicMock()
    parent.close_task_detail = MagicMock()
    return parent


@pytest.fixture
def detail_panel(mock_parent, db_manager) -> TaskDetailPanel:
    panel = TaskDetailPanel(
        master=mock_parent,
        db_manager=db_manager,
        on_save_callback=mock_parent.refresh_all_quadrants,
        on_close_callback=mock_parent.close_task_detail,
    )
    return panel


def test_detail_panel_load(
    detail_panel: TaskDetailPanel, db_manager: DatabaseManager
) -> None:
    # 1. Insert a mock task
    task, matrix = db_manager.create_task(
        title="Test Task Title",
        notes="Important extra notes",
        due_date="2026-07-20",
        quadrant="schedule",
    )

    # 2. Insert mock transcripts to generate context
    # Create session
    db_manager.create_session("session1", 1000.0)
    from taskify.storage.models import TranscriptSegment

    db_manager.insert_transcripts(
        [
            TranscriptSegment(
                session_id="session1",
                text="Need to finish test task title",
                confidence=0.95,
                start_time=1001.0,
                end_time=1005.0,
            )
        ]
    )

    # Load task into panel
    detail_panel.load_task(task.id)

    # Verify UI values are populated
    assert detail_panel.title_entry.get() == "Test Task Title"
    assert detail_panel.notes_box.get() == "Important extra notes"
    assert detail_panel.due_date_entry.get() == "2026-07-20"
    assert detail_panel.status_var.get() == "pending"


def test_detail_panel_auto_save_on_blur(
    detail_panel: TaskDetailPanel, db_manager: DatabaseManager
) -> None:
    # Insert task
    task, matrix = db_manager.create_task(
        title="Original Title",
        notes="Original Notes",
        due_date="2026-07-18",
        quadrant="do_first",
    )

    # Load it
    detail_panel.load_task(task.id)

    # Edit fields
    detail_panel.title_entry.delete()
    detail_panel.title_entry.insert(0, "Updated Title")

    detail_panel.notes_box.delete()
    detail_panel.notes_box.insert("1.0", "Updated Notes")

    detail_panel.due_date_entry.delete()
    detail_panel.due_date_entry.insert(0, "2026-07-22")

    detail_panel.status_var.set("completed")

    # Trigger save (simulate FocusOut/blur)
    detail_panel.save_task()

    # Re-fetch from database to verify persistence
    updated_data = db_manager.get_task(task.id)
    assert updated_data is not None
    updated_task, updated_matrix = updated_data

    assert updated_task.title == "Updated Title"
    assert updated_task.notes == "Updated Notes"
    assert updated_task.due_date == "2026-07-22"
    assert updated_task.status == "completed"
    assert detail_panel.on_save.called


def test_detail_panel_quadrant_override(
    detail_panel: TaskDetailPanel, db_manager: DatabaseManager
) -> None:
    task, matrix = db_manager.create_task(
        title="Heuristic Task",
        notes="...",
        due_date="",
        quadrant="schedule",
    )

    detail_panel.load_task(task.id)

    # Trigger dropdown change
    detail_panel._on_quadrant_changed("Do First")

    # Verify immediate override and user_override = 1 in database
    updated_data = db_manager.get_task(task.id)
    assert updated_data is not None
    updated_task, updated_matrix = updated_data

    assert updated_matrix.quadrant == "do_first"
    assert updated_matrix.user_override is True
    assert detail_panel.on_save.called


def test_detail_panel_close(
    detail_panel: TaskDetailPanel, db_manager: DatabaseManager
) -> None:
    task, matrix = db_manager.create_task(
        title="Closing Task",
        notes="",
        due_date="",
        quadrant="eliminate",
    )

    detail_panel.load_task(task.id)
    detail_panel.title_entry.delete()
    detail_panel.title_entry.insert(0, "Closed Title")

    # Close panel
    detail_panel.close_panel()

    # Verify save was triggered
    updated_data = db_manager.get_task(task.id)
    assert updated_data is not None
    assert updated_data[0].title == "Closed Title"
    assert detail_panel.on_close.called


def test_task_card_left_click_opens_details(db_manager: DatabaseManager) -> None:
    task = TaskRecord(
        id=42,
        title="Left Click Task",
        notes="Test details display",
        due_date="2026-07-25",
        status="pending",
    )

    mock_on_action = MagicMock()
    mock_scroll = MagicMock()

    # Create task card
    card = TaskCard(master=mock_scroll, task=task, on_action=mock_on_action)

    # Simulate mouse left-click on the card
    card._on_click(MagicMock())

    # Verify edit callback was invoked with task id
    mock_on_action.assert_called_once_with("edit", 42)
