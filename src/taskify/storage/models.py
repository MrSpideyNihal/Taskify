"""Database data transfer objects (DTOs) representing SQLite table records."""

from dataclasses import dataclass
from typing import Any, Self


@dataclass
class SessionRecord:
    """Represents a voice capture session record."""

    id: str
    start_time: float
    end_time: float | None = None
    created_at: str | None = None

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> Self:
        """Instantiate class from raw SQLite query row tuple."""
        return cls(
            id=str(row[0]),
            start_time=float(row[1]),
            end_time=float(row[2]) if row[2] is not None else None,
            created_at=str(row[3]) if row[3] is not None else None,
        )


@dataclass
class TranscriptSegment:
    """Represents a transcribed speech segment."""

    session_id: str
    text: str
    confidence: float
    start_time: float
    end_time: float
    id: int | None = None
    processed: bool = False
    created_at: str | None = None

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> Self:
        """Instantiate class from raw SQLite query row tuple."""
        return cls(
            id=int(row[0]),
            session_id=str(row[1]),
            text=str(row[2]),
            confidence=float(row[3]),
            start_time=float(row[4]),
            end_time=float(row[5]),
            processed=bool(row[6]),
            created_at=str(row[7]) if row[7] is not None else None,
        )


@dataclass
class TaskRecord:
    """Represents an extracted personal task."""

    title: str
    notes: str = ""
    due_date: str = ""
    status: str = "pending"
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> Self:
        """Instantiate class from raw SQLite query row tuple."""
        return cls(
            id=int(row[0]),
            title=str(row[1]),
            notes=str(row[2]),
            due_date=str(row[3]),
            status=str(row[4]),
            created_at=str(row[5]) if row[5] is not None else None,
            updated_at=str(row[6]) if row[6] is not None else None,
        )


@dataclass
class MatrixEntry:
    """Eisenhower Matrix quadrant mapping for a task."""

    task_id: int
    quadrant: str
    user_override: bool = False

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> Self:
        """Instantiate class from raw SQLite query row tuple."""
        return cls(
            task_id=int(row[0]),
            quadrant=str(row[1]),
            user_override=bool(row[2]),
        )
