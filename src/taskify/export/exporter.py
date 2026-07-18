"""Tasks exporter supporting Markdown and JSON formats with flexible filtering."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from taskify.storage.database import DatabaseManager

# User-facing labels for application quadrants
QUADRANT_LABELS = {
    "do_first": "Do First (Urgent & Important)",
    "schedule": "Schedule (Important & Not Urgent)",
    "delegate": "Delegate (Urgent & Not Important)",
    "eliminate": "Eliminate (Not Urgent & Not Important)",
}


def parse_created_at(dt_str: str | None) -> datetime | None:
    """Parse date-time strings safely from various potential database formats."""
    if not dt_str:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
    ):
        try:
            # Strip timezone Z indicator if present to parse cleanly
            clean_str = dt_str.replace("Z", "")
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
    return None


def export_tasks_to_file(
    db: DatabaseManager,
    filepath: Path,
    format: str,
    quadrant: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Query, filter, and serialize tasks to a file.

    Args:
        db (DatabaseManager): Open SQLite database manager.
        filepath (Path): Target file path destination.
        format (str): Output format ("markdown" or "json").
        quadrant (str, optional): Target app-level quadrant key.
        start_date (datetime, optional): Start range filter for creation date.
        end_date (datetime, optional): End range filter for creation date.

    Returns:
        int: Total number of tasks serialized.
    """
    all_records = db.get_all_tasks()
    matching_tasks = []

    for task, entry in all_records:
        # 1. Filter by quadrant
        if quadrant and entry.quadrant != quadrant:
            continue

        # 2. Filter by date range
        task_dt = parse_created_at(task.created_at)
        if task_dt:
            if start_date and task_dt < start_date:
                continue
            if end_date and task_dt > end_date:
                continue

        # Fetch matching transcript context
        assert task.id is not None
        excerpt = db.get_transcript_excerpt_for_task(task.id)

        matching_tasks.append((task, entry, excerpt))

    # Reverse order to export in chronological order (oldest first)
    matching_tasks.reverse()

    if format.lower() == "json":
        data = []
        for task, entry, excerpt in matching_tasks:
            data.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "notes": task.notes or "",
                    "due_date": task.due_date or "",
                    "quadrant": entry.quadrant,
                    "completed": task.status == "completed",
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "transcript_excerpt": excerpt,
                }
            )

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    elif format.lower() == "markdown":
        lines = []
        lines.append("# Taskify Tasks Export")
        lines.append("")
        exported_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"- **Exported On:** {exported_str}")

        filters = []
        if quadrant:
            filters.append(f"Quadrant: {QUADRANT_LABELS.get(quadrant, quadrant)}")
        if start_date:
            filters.append(f"From: {start_date.strftime('%Y-%m-%d')}")
        if end_date:
            filters.append(f"To: {end_date.strftime('%Y-%m-%d')}")

        if filters:
            lines.append(f"- **Filters:** {', '.join(filters)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for task, entry, excerpt in matching_tasks:
            checkbox = "[x]" if task.status == "completed" else "[ ]"
            lines.append(f"- {checkbox} **{task.title}**")
            q_label = QUADRANT_LABELS.get(entry.quadrant, entry.quadrant)
            lines.append(f"  - **Quadrant:** {q_label}")
            if task.due_date:
                lines.append(f"  - **Due Date:** {task.due_date}")
            if task.created_at:
                lines.append(f"  - **Created At:** {task.created_at}")
            if task.notes:
                # Indent notes properly
                clean_notes = task.notes.replace("\n", "\n    ")
                lines.append(f"  - **Notes:** {clean_notes}")
            if excerpt and excerpt != "No matching transcript context found.":
                lines.append(f"  - **Transcript Excerpt:** *{excerpt}*")
            lines.append("")

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    else:
        raise ValueError(f"Unsupported export format: {format}")

    return len(matching_tasks)
