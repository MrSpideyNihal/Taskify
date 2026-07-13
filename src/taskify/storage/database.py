"""SQLite database manager and versioned schema migration runner."""

import importlib.resources
import re
import sqlite3
import threading
from pathlib import Path

from taskify.storage.models import (
    MatrixEntry,
    SessionRecord,
    TaskRecord,
    TranscriptSegment,
)


class DatabaseManager:
    """Thread-safe SQLite database manager for task and transcript persistence."""

    def __init__(self, db_path: Path) -> None:
        """Initialize database manager, creating parent directories if missing.

        Args:
            db_path (Path): Destination SQLite file path.
        """
        self.db_path = db_path
        self._lock = threading.Lock()

        # Create parent directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize connection thread-safely
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, timeout=10.0
        )
        self._conn.row_factory = sqlite3.Row

        # Apply basic optimizations
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.commit()

        # Run migrations on startup
        self.run_migrations()

    def run_migrations(self) -> None:
        """Run SQL migration scripts sequentially to construct schemas."""
        with self._lock:
            # Create migration tracking table if not present
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._conn.commit()

            # Retrieve applied versions
            cursor = self._conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version ASC;"
            )
            applied_versions = {row["version"] for row in cursor.fetchall()}

            # Locate migration resources
            migration_files = importlib.resources.files(
                "taskify.storage.migrations"
            )

            # Filter and parse files starting with 4 digits (e.g. 0001_xxx.sql)
            migrations_to_apply = []
            for file_path in migration_files.iterdir():
                if file_path.name.endswith(".sql"):
                    match = re.match(r"^(\d{4})_", file_path.name)
                    if match:
                        version = int(match.group(1))
                        if version not in applied_versions:
                            migrations_to_apply.append((version, file_path))

            # Sort migrations by version code
            migrations_to_apply.sort(key=lambda item: item[0])

            # Apply migrations sequentially
            for version, file_ref in migrations_to_apply:
                sql_script = file_ref.read_text(encoding="utf-8")
                try:
                    self._conn.executescript(sql_script)
                    self._conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES (?);",
                        (version,),
                    )
                    self._conn.commit()
                except sqlite3.Error as e:
                    self._conn.rollback()
                    raise RuntimeError(
                        f"Failed to apply database migration version {version}: {e}"
                    ) from e

    def close(self) -> None:
        """Close connection to database."""
        with self._lock:
            self._conn.close()

    # --- Sessions CRUD ---

    def create_session(self, session_id: str, start_time: float) -> SessionRecord:
        """Insert a voice capture session.

        Args:
            session_id (str): Unique session identifier.
            start_time (float): Session start epoch timestamp.

        Returns:
            SessionRecord: The created session object.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, start_time) VALUES (?, ?);",
                (session_id, start_time),
            )
            self._conn.commit()

            cursor = self._conn.execute(
                "SELECT id, start_time, end_time, created_at "
                "FROM sessions WHERE id = ?;",
                (session_id,),
            )
            row = cursor.fetchone()
            return SessionRecord.from_row(tuple(row))

    def close_session(self, session_id: str, end_time: float) -> None:
        """Update session end time to mark completion.

        Args:
            session_id (str): Existing session identifier.
            end_time (float): Session end epoch timestamp.
        """
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET end_time = ? WHERE id = ?;",
                (end_time, session_id),
            )
            self._conn.commit()

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Retrieve session record by identifier.

        Args:
            session_id (str): Unique session identifier.

        Returns:
            SessionRecord, optional: Session object if exists.
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, start_time, end_time, created_at "
                "FROM sessions WHERE id = ?;",
                (session_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return SessionRecord.from_row(tuple(row))

    # --- Transcripts CRUD ---

    def insert_transcripts(self, segments: list[TranscriptSegment]) -> None:
        """Batch insert transcript segments.

        Args:
            segments (list[TranscriptSegment]): Speech segment list.
        """
        if not segments:
            return

        with self._lock:
            try:
                self._conn.executemany(
                    """
                    INSERT INTO transcripts (
                        session_id, text, confidence, start_time, end_time, processed
                    )
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    [
                        (
                            s.session_id,
                            s.text,
                            s.confidence,
                            s.start_time,
                            s.end_time,
                            1 if s.processed else 0,
                        )
                        for s in segments
                    ],
                )
                self._conn.commit()
            except sqlite3.Error as e:
                self._conn.rollback()
                raise e

    def get_unprocessed_transcripts(self) -> list[TranscriptSegment]:
        """Fetch all transcript segments that are not processed by task extractor.

        Returns:
            list[TranscriptSegment]: Unprocessed segments list.
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT id, session_id, text, confidence, start_time, end_time,
                       processed, created_at
                FROM transcripts WHERE processed = 0 ORDER BY id ASC;
                """
            )
            rows = cursor.fetchall()
            return [TranscriptSegment.from_row(tuple(row)) for row in rows]

    def mark_transcripts_processed(self, ids: list[int]) -> None:
        """Update processed state of transcript segments.

        Args:
            ids (list[int]): Transcript primary key list.
        """
        if not ids:
            return

        with self._lock:
            try:
                # Construct query dynamically to support bulk values
                placeholders = ",".join("?" for _ in ids)
                self._conn.execute(
                    "UPDATE transcripts SET processed = 1 "
                    f"WHERE id IN ({placeholders});",
                    ids,
                )
                self._conn.commit()
            except sqlite3.Error as e:
                self._conn.rollback()
                raise e

    # --- Tasks CRUD ---

    def create_task(
        self, title: str, notes: str, due_date: str, quadrant: str
    ) -> tuple[TaskRecord, MatrixEntry]:
        """Insert task and map to matrix quadrant in a single transaction.

        Args:
            title (str): Task short summary.
            notes (str): Inline task remarks.
            due_date (str): Expected deadline date.
            quadrant (str): Matrix quadrant selection.

        Returns:
            tuple[TaskRecord, MatrixEntry]: Created records.
        """
        with self._lock:
            try:
                # Insert task details
                cursor = self._conn.execute(
                    "INSERT INTO tasks (title, notes, due_date) VALUES (?, ?, ?);",
                    (title, notes, due_date),
                )
                task_id = cursor.lastrowid
                if task_id is None:
                    raise sqlite3.Error("Failed to retrieve generated task ID.")

                # Insert matrix association
                self._conn.execute(
                    "INSERT INTO matrix_entries (task_id, quadrant) VALUES (?, ?);",
                    (task_id, quadrant),
                )
                self._conn.commit()

                # Re-fetch models
                task_cursor = self._conn.execute(
                    "SELECT id, title, notes, due_date, status, created_at, "
                    "updated_at FROM tasks WHERE id = ?;",
                    (task_id,),
                )
                task_row = task_cursor.fetchone()

                matrix_cursor = self._conn.execute(
                    "SELECT task_id, quadrant, user_override "
                    "FROM matrix_entries WHERE task_id = ?;",
                    (task_id,),
                )
                matrix_row = matrix_cursor.fetchone()

                return (
                    TaskRecord.from_row(tuple(task_row)),
                    MatrixEntry.from_row(tuple(matrix_row)),
                )
            except sqlite3.Error as e:
                self._conn.rollback()
                raise e

    def update_task(
        self, task_id: int, title: str, notes: str, due_date: str, status: str
    ) -> None:
        """Update task details.

        Args:
            task_id (int): Existing task identifier.
            title (str): Updated task title.
            notes (str): Updated task notes.
            due_date (str): Updated task due date.
            status (str): Updated task status.
        """
        with self._lock:
            try:
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET title = ?, notes = ?, due_date = ?, status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (title, notes, due_date, status, task_id),
                )
                self._conn.commit()
            except sqlite3.Error as e:
                self._conn.rollback()
                raise e

    def delete_task(self, task_id: int) -> None:
        """Delete task from database (cascades automatically to matrix entries).

        Args:
            task_id (int): Target task identifier.
        """
        with self._lock:
            try:
                self._conn.execute("DELETE FROM tasks WHERE id = ?;", (task_id,))
                self._conn.commit()
            except sqlite3.Error as e:
                self._conn.rollback()
                raise e

    def get_task(self, task_id: int) -> tuple[TaskRecord, MatrixEntry] | None:
        """Retrieve single task details with quadrant association.

        Args:
            task_id (int): Target task identifier.

        Returns:
            tuple, optional: (TaskRecord, MatrixEntry) if exists.
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT t.id, t.title, t.notes, t.due_date, t.status,
                       t.created_at, t.updated_at,
                       m.task_id, m.quadrant, m.user_override
                FROM tasks t
                JOIN matrix_entries m ON t.id = m.task_id
                WHERE t.id = ?;
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            # Split columns into corresponding models
            t_row = (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
            )
            m_row = (row[7], row[8], row[9])

            return TaskRecord.from_row(t_row), MatrixEntry.from_row(m_row)

    def get_tasks_in_quadrant(
        self, quadrant: str
    ) -> list[tuple[TaskRecord, MatrixEntry]]:
        """Fetch all tasks mapped to a specific matrix quadrant.

        Args:
            quadrant (str): Matrix quadrant selection.

        Returns:
            list[tuple[TaskRecord, MatrixEntry]]: List of tasks matched.
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT t.id, t.title, t.notes, t.due_date, t.status,
                       t.created_at, t.updated_at,
                       m.task_id, m.quadrant, m.user_override
                FROM tasks t
                JOIN matrix_entries m ON t.id = m.task_id
                WHERE m.quadrant = ?
                ORDER BY t.created_at DESC;
                """,
                (quadrant,),
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                t_row = (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                )
                m_row = (row[7], row[8], row[9])
                results.append(
                    (TaskRecord.from_row(t_row), MatrixEntry.from_row(m_row))
                )
            return results

    def get_all_tasks(self) -> list[tuple[TaskRecord, MatrixEntry]]:
        """Fetch all tasks with their matrix quadrant assignments.

        Returns:
            list[tuple[TaskRecord, MatrixEntry]]: Complete checklist.
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT t.id, t.title, t.notes, t.due_date, t.status,
                       t.created_at, t.updated_at,
                       m.task_id, m.quadrant, m.user_override
                FROM tasks t
                JOIN matrix_entries m ON t.id = m.task_id
                ORDER BY t.created_at DESC;
                """
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                t_row = (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                )
                m_row = (row[7], row[8], row[9])
                results.append(
                    (TaskRecord.from_row(t_row), MatrixEntry.from_row(m_row))
                )
            return results

    def override_matrix_quadrant(self, task_id: int, quadrant: str) -> None:
        """Manually move task to another quadrant, raising user override state.

        Args:
            task_id (int): Existing task identifier.
            quadrant (str): Target quadrant name.
        """
        with self._lock:
            try:
                self._conn.execute(
                    """
                    UPDATE matrix_entries
                    SET quadrant = ?, user_override = 1
                    WHERE task_id = ?;
                    """,
                    (quadrant, task_id),
                )
                self._conn.commit()
            except sqlite3.Error as e:
                self._conn.rollback()
                raise e
