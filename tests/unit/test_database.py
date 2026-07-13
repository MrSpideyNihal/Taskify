"""Unit tests for SQLite database manager and schemas."""

import sqlite3
import threading
from pathlib import Path
import pytest
from taskify.storage import (
    DatabaseManager,
    MatrixEntry,
    SessionRecord,
    TaskRecord,
    TranscriptSegment,
)


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Fixture returning a temporary filepath for database testing."""
    return tmp_path / "test_taskify.db"


def test_migration_and_tables_creation(temp_db_path: Path) -> None:
    """Test that database initializes and runs migrations to create tables."""
    db = DatabaseManager(temp_db_path)
    try:
        # Connect to DB directly to verify tables exist
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()

        # Check for tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions';"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts';"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks';"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='matrix_entries';"
        )
        assert cursor.fetchone() is not None

        conn.close()
    finally:
        db.close()


def test_migrations_idempotency(temp_db_path: Path) -> None:
    """Test that running migrations multiple times doesn't cause errors."""
    db = DatabaseManager(temp_db_path)
    try:
        # Re-run migration method directly
        db.run_migrations()
    finally:
        db.close()


def test_sessions_crud(temp_db_path: Path) -> None:
    """Test session creation, retrieval, and closing operations."""
    db = DatabaseManager(temp_db_path)
    try:
        session_id = "test-session-123"
        start_time = 1718000000.0

        # Create
        session = db.create_session(session_id, start_time)
        assert session.id == session_id
        assert session.start_time == start_time
        assert session.end_time is None

        # Retrieve
        retrieved = db.get_session(session_id)
        assert retrieved is not None
        assert retrieved.id == session_id
        assert retrieved.start_time == start_time

        # Close
        end_time = 1718003600.0
        db.close_session(session_id, end_time)

        closed = db.get_session(session_id)
        assert closed is not None
        assert closed.end_time == end_time

        # Get non-existent
        assert db.get_session("unknown") is None
    finally:
        db.close()


def test_transcripts_crud(temp_db_path: Path) -> None:
    """Test transcript segment operations including marking processed."""
    db = DatabaseManager(temp_db_path)
    try:
        # Setup session
        session_id = "sess-abc"
        db.create_session(session_id, 1000.0)

        # Batch insert
        segments = [
            TranscriptSegment(
                session_id=session_id,
                text="This is a test task",
                confidence=0.95,
                start_time=1.0,
                end_time=3.5,
            ),
            TranscriptSegment(
                session_id=session_id,
                text="Another task here",
                confidence=0.88,
                start_time=4.0,
                end_time=6.2,
            ),
        ]
        db.insert_transcripts(segments)

        # Retrieve unprocessed
        unprocessed = db.get_unprocessed_transcripts()
        assert len(unprocessed) == 2
        assert unprocessed[0].text == "This is a test task"
        assert unprocessed[1].text == "Another task here"
        assert not unprocessed[0].processed

        # Mark processed
        ids = [s.id for s in unprocessed if s.id is not None]
        assert len(ids) == 2
        db.mark_transcripts_processed(ids)

        # Check unprocessed is now empty
        assert len(db.get_unprocessed_transcripts()) == 0
    finally:
        db.close()


def test_tasks_crud(temp_db_path: Path) -> None:
    """Test task and matrix entry lifecycle operations."""
    db = DatabaseManager(temp_db_path)
    try:
        # Create task
        title = "Complete report writing"
        notes = "Needs to be finished before Friday morning"
        due_date = "2026-07-17"
        quadrant = "urgent_important"

        task, matrix = db.create_task(title, notes, due_date, quadrant)

        assert task.id is not None
        assert task.title == title
        assert task.notes == notes
        assert task.due_date == due_date
        assert task.status == "pending"

        assert matrix.task_id == task.id
        assert matrix.quadrant == quadrant
        assert not matrix.user_override

        # Retrieve single task
        record = db.get_task(task.id)
        assert record is not None
        ret_task, ret_matrix = record
        assert ret_task.title == title
        assert ret_matrix.quadrant == quadrant

        # Get all tasks
        all_tasks = db.get_all_tasks()
        assert len(all_tasks) == 1
        assert all_tasks[0][0].id == task.id

        # Update task
        db.update_task(
            task.id, "Complete report", "ASAP", "2026-07-16", "completed"
        )
        updated = db.get_task(task.id)
        assert updated is not None
        assert updated[0].title == "Complete report"
        assert updated[0].notes == "ASAP"
        assert updated[0].status == "completed"

        # Check tasks by quadrant
        urgent_tasks = db.get_tasks_in_quadrant("urgent_important")
        assert len(urgent_tasks) == 1
        assert urgent_tasks[0][0].id == task.id

        empty_quadrant = db.get_tasks_in_quadrant("neither")
        assert len(empty_quadrant) == 0

        # Override quadrant
        db.override_matrix_quadrant(task.id, "neither")
        overridden = db.get_task(task.id)
        assert overridden is not None
        assert overridden[1].quadrant == "neither"
        assert overridden[1].user_override

        # Delete task
        db.delete_task(task.id)
        assert db.get_task(task.id) is None

        # Assert cascade deletion occurred on matrix_entries
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM matrix_entries WHERE task_id = ?;", (task.id,))
        assert cursor.fetchone() is None
        conn.close()
    finally:
        db.close()


def test_database_thread_safety(temp_db_path: Path) -> None:
    """Verify thread-safe database inserts under concurrency."""
    db = DatabaseManager(temp_db_path)
    try:
        # Setup session
        session_id = "concurrent-sess"
        db.create_session(session_id, 1000.0)

        num_threads = 5
        inserts_per_thread = 10
        errors = []

        def worker(thread_idx: int) -> None:
            try:
                for i in range(inserts_per_thread):
                    segment = TranscriptSegment(
                        session_id=session_id,
                        text=f"Thread {thread_idx} segment {i}",
                        confidence=0.9,
                        start_time=float(i),
                        end_time=float(i + 1),
                    )
                    db.insert_transcripts([segment])
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        unprocessed = db.get_unprocessed_transcripts()
        assert len(unprocessed) == num_threads * inserts_per_thread
    finally:
        db.close()
