"""LLM domain models: TaskItem and MatrixQuadrant."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MatrixQuadrant(str, Enum):
    """Eisenhower Matrix quadrant classification."""

    DO_FIRST = "do_first"         # Urgent + Important
    SCHEDULE = "schedule"         # Not Urgent + Important
    DELEGATE = "delegate"         # Urgent + Not Important
    ELIMINATE = "eliminate"       # Not Urgent + Not Important

    @classmethod
    def from_string(cls, value: str) -> MatrixQuadrant:
        """Parse a quadrant string case-insensitively.

        Args:
            value (str): Raw quadrant string from LLM or config.

        Returns:
            MatrixQuadrant: Matched enum member.

        Raises:
            ValueError: If the string does not match any quadrant.
        """
        normalised = value.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == normalised:
                return member
        raise ValueError(
            f"Unknown quadrant '{value}'. "
            f"Valid values: {[m.value for m in cls]}"
        )


@dataclass
class TaskItem:
    """A single task extracted from a transcript segment."""

    title: str
    notes: str = ""
    due_date: str = ""
    quadrant: MatrixQuadrant = MatrixQuadrant.SCHEDULE
    source_transcript: str = ""
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)
