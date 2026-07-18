"""Unit tests for the task export subpackage."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator

import pytest

from taskify.config import (
    AudioSettings,
    LLMSettings,
    LoggingSettings,
    Settings,
    STTSettings,
    StorageSettings,
)
from taskify.export import export_tasks_to_file
from taskify.storage.database import DatabaseManager
from taskify.storage.models import TaskRecord, TranscriptSegment


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Fixture returning settings pointing to temp directories."""
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
            data_dir=tmp_path / "data",
            log_dir=tmp_path / "logs",
        ),
        logging=LoggingSettings(
            level="INFO",
            debug_llm=False,
        ),
    )


@pytest.fixture
def db(test_settings: Settings) -> Generator[DatabaseManager, None, None]:
    """Fixture returning an initialized DatabaseManager."""
    db_path = test_settings.storage.data_dir / "taskify.db"
    test_settings.storage.data_dir.mkdir(parents=True, exist_ok=True)
    manager = DatabaseManager(db_path)

    # Seed data
    # Create session
    session_id = "test-session"
    manager.create_session(session_id, start_time=1000.0)

    # Insert transcript segment
    segment = TranscriptSegment(
        session_id=session_id,
        text="Buy some fresh groceries immediately.",
        confidence=0.9,
        start_time=1.0,
        end_time=3.0,
        created_at="2026-07-18 12:00:00",
    )
    manager.insert_transcripts([segment])

    # Force transcript timestamp to align with task timestamp for excerpt extraction
    with manager._lock:
        manager._conn.execute(
            "UPDATE transcripts SET created_at = '2026-07-18 11:58:00' WHERE session_id = ?;",
            (session_id,),
        )
        manager._conn.commit()

    # Insert tasks (using manager methods directly)
    # Task 1: Do First
    t1 = manager.create_task(
        title="Buy groceries",
        notes="Milk and bread",
        due_date="2026-07-19",
        quadrant="do_first",
    )
    # Force task 1 timestamp for date range check
    with manager._lock:
        manager._conn.execute(
            "UPDATE tasks SET created_at = '2026-07-18 12:00:05' WHERE id = ?;", (t1[0].id,)
        )
        manager._conn.commit()

    # Task 2: Schedule
    t2 = manager.create_task(
        title="Plan roadmap",
        notes="",
        due_date="",
        quadrant="schedule",
    )
    # Force task 2 timestamp
    with manager._lock:
        manager._conn.execute(
            "UPDATE tasks SET created_at = '2026-07-19 14:00:00' WHERE id = ?;", (t2[0].id,)
        )
        manager._conn.commit()

    yield manager
    manager.close()


def test_export_to_json(db: DatabaseManager, tmp_path: Path) -> None:
    """Test exporting tasks to JSON format."""
    filepath = tmp_path / "export.json"
    count = export_tasks_to_file(db, filepath, format="json")

    assert count == 2
    assert filepath.exists()

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 2
    # Chronological order assertion (oldest first: Task 1 then Task 2)
    assert data[0]["title"] == "Buy groceries"
    assert data[0]["quadrant"] == "do_first"
    assert data[0]["transcript_excerpt"] == "Buy some fresh groceries immediately."
    assert data[1]["title"] == "Plan roadmap"


def test_export_to_markdown(db: DatabaseManager, tmp_path: Path) -> None:
    """Test exporting tasks to Markdown format."""
    filepath = tmp_path / "export.md"
    count = export_tasks_to_file(db, filepath, format="markdown")

    assert count == 2
    assert filepath.exists()

    content = filepath.read_text(encoding="utf-8")
    assert "# Taskify Tasks Export" in content
    assert "- [ ] **Buy groceries**" in content
    assert "  - **Quadrant:** Do First (Urgent & Important)" in content
    assert "  - **Transcript Excerpt:** *Buy some fresh groceries immediately.*" in content
    assert "- [ ] **Plan roadmap**" in content


def test_export_with_quadrant_filter(db: DatabaseManager, tmp_path: Path) -> None:
    """Test exporting tasks filtered by quadrant."""
    filepath = tmp_path / "export.json"
    count = export_tasks_to_file(db, filepath, format="json", quadrant="do_first")

    assert count == 1
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 1
    assert data[0]["title"] == "Buy groceries"


def test_export_with_date_range_filters(db: DatabaseManager, tmp_path: Path) -> None:
    """Test exporting tasks filtered by start and end date ranges."""
    filepath = tmp_path / "export.json"

    # Filter for July 18th
    start = datetime(2026, 7, 18, 0, 0, 0)
    end = datetime(2026, 7, 18, 23, 59, 59)

    count = export_tasks_to_file(db, filepath, format="json", start_date=start, end_date=end)
    assert count == 1

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data[0]["title"] == "Buy groceries"

    # Filter for July 19th
    start = datetime(2026, 7, 19, 0, 0, 0)
    end = datetime(2026, 7, 19, 23, 59, 59)

    count = export_tasks_to_file(db, filepath, format="json", start_date=start, end_date=end)
    assert count == 1

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data[0]["title"] == "Plan roadmap"


def test_export_invalid_format(db: DatabaseManager, tmp_path: Path) -> None:
    """Test exporter raises ValueError for unsupported formats."""
    filepath = tmp_path / "export.txt"
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_tasks_to_file(db, filepath, format="unsupported")
