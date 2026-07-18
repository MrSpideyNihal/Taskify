"""Task detail sidebar drawer panel with inline editing and auto-save on blur."""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime
from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from taskify.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

# Premium styling constants matching main window theme
BG_COLOR = "#121214"
CARD_BG = "#1A1A1E"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#9999A1"
BORDER_COLOR = "#2D2D34"

# Option menu display to key quadrant mapping
_QUADRANT_DISPLAY_TO_KEY = {
    "Do First": "do_first",
    "Schedule": "schedule",
    "Delegate": "delegate",
    "Eliminate": "eliminate",
}
_QUADRANT_KEY_TO_DISPLAY = {v: k for k, v in _QUADRANT_DISPLAY_TO_KEY.items()}


class TaskDetailPanel(ctk.CTkFrame):
    """Inline side drawer showing task transcript context and editable fields."""

    def __init__(
        self,
        master: ctk.CTkFrame,
        db_manager: DatabaseManager,
        on_save_callback: ctk.Callable[[], None],
        on_close_callback: ctk.Callable[[], None],
    ) -> None:
        """Initialize task detail sidebar panel.

        Args:
            master (CTkFrame): Parent main window layout grid.
            db_manager (DatabaseManager): Active SQLite database connection manager.
            on_save_callback (Callable): Event hook called when a task is saved.
            on_close_callback (Callable): Event hook called when panel is closed.
        """
        super().__init__(
            master,
            fg_color=CARD_BG,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=12,
            width=340,
        )
        self._db = db_manager
        self.on_save = on_save_callback
        self.on_close = on_close_callback

        self.task_id: int | None = None
        self._current_title: str = ""
        self._current_notes: str = ""
        self._current_due_date: str = ""
        self._current_quadrant: str = ""
        self._current_status: str = ""

        # Avoid auto-saving during initial load
        self._loading: bool = False

        # Set up grid layout (column 0 gets all space)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Content area scrollable

        # Header Row
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        self.header_label = ctk.CTkLabel(
            header_frame,
            text="Task Details",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        )
        self.header_label.grid(row=0, column=0, sticky="w")

        self.close_btn = ctk.CTkButton(
            header_frame,
            text="✕",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT_SECONDARY,
            hover_color=BORDER_COLOR,
            fg_color="transparent",
            width=30,
            height=30,
            corner_radius=15,
            command=self.close_panel,
        )
        self.close_btn.grid(row=0, column=1, sticky="e")

        # Scrollable container for detail fields
        self.scroll_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=TEXT_SECONDARY,
        )
        self.scroll_container.grid(row=1, column=0, padx=8, pady=(0, 16), sticky="nsew")
        self.scroll_container.grid_columnconfigure(0, weight=1)

        # 1. Transcript Excerpt Context Area
        ctk.CTkLabel(
            self.scroll_container,
            text="Source Transcript Context:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        self.excerpt_box = ctk.CTkTextbox(
            self.scroll_container,
            height=80,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SECONDARY,
            fg_color=BG_COLOR,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6,
            wrap="word",
        )
        self.excerpt_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.excerpt_box.configure(state="disabled")

        # 2. Editable Title Field
        ctk.CTkLabel(
            self.scroll_container,
            text="Title:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=2, column=0, padx=12, pady=(4, 2), sticky="w")

        self.title_entry = ctk.CTkEntry(
            self.scroll_container,
            font=ctk.CTkFont(size=13),
            text_color=TEXT_PRIMARY,
            fg_color=BG_COLOR,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6,
        )
        self.title_entry.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.title_entry.bind("<FocusOut>", lambda e: self.save_task())
        self.title_entry.bind("<Return>", lambda e: self.focus_set())  # Commit on Enter

        # 3. Editable Notes Field
        ctk.CTkLabel(
            self.scroll_container,
            text="Notes:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=4, column=0, padx=12, pady=(4, 2), sticky="w")

        self.notes_box = ctk.CTkTextbox(
            self.scroll_container,
            height=100,
            font=ctk.CTkFont(size=12),
            text_color=TEXT_PRIMARY,
            fg_color=BG_COLOR,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6,
            wrap="word",
        )
        self.notes_box.grid(row=5, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.notes_box.bind("<FocusOut>", lambda e: self.save_task())

        # 4. Due Date Field
        ctk.CTkLabel(
            self.scroll_container,
            text="Due Date (YYYY-MM-DD):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=6, column=0, padx=12, pady=(4, 2), sticky="w")

        self.due_date_entry = ctk.CTkEntry(
            self.scroll_container,
            font=ctk.CTkFont(size=13),
            text_color=TEXT_PRIMARY,
            placeholder_text="YYYY-MM-DD",
            fg_color=BG_COLOR,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=6,
        )
        self.due_date_entry.grid(row=7, column=0, padx=12, pady=(0, 12), sticky="ew")
        self.due_date_entry.bind("<FocusOut>", lambda e: self.save_task())
        self.due_date_entry.bind("<Return>", lambda e: self.focus_set())

        # 5. Eisenhower Quadrant Option Menu
        ctk.CTkLabel(
            self.scroll_container,
            text="Matrix Quadrant Override:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).grid(row=8, column=0, padx=12, pady=(4, 2), sticky="w")

        self.quadrant_menu = ctk.CTkOptionMenu(
            self.scroll_container,
            values=list(_QUADRANT_DISPLAY_TO_KEY.keys()),
            command=self._on_quadrant_changed,
            button_color=BORDER_COLOR,
            button_hover_color=TEXT_SECONDARY,
            fg_color=BG_COLOR,
            text_color=TEXT_PRIMARY,
            corner_radius=6,
        )
        self.quadrant_menu.grid(row=9, column=0, padx=12, pady=(0, 12), sticky="ew")

        # 6. Status Checkbox
        self.status_var = tk.StringVar(value="pending")
        self.status_checkbox = ctk.CTkCheckBox(
            self.scroll_container,
            text="Mark Done",
            font=ctk.CTkFont(size=12, weight="bold"),
            variable=self.status_var,
            onvalue="completed",
            offvalue="pending",
            command=self.save_task,
            text_color=TEXT_PRIMARY,
            fg_color=BORDER_COLOR,
            hover_color=TEXT_SECONDARY,
            border_color=TEXT_SECONDARY,
            corner_radius=4,
        )
        self.status_checkbox.grid(row=10, column=0, padx=12, pady=(4, 16), sticky="w")

        # Divider
        divider = ctk.CTkFrame(self.scroll_container, height=1, fg_color=BORDER_COLOR)
        divider.grid(row=11, column=0, padx=12, pady=(0, 16), sticky="ew")

        # Timestamps Labels
        self.created_label = ctk.CTkLabel(
            self.scroll_container,
            text="Created: --",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.created_label.grid(row=12, column=0, padx=12, pady=(0, 4), sticky="w")

        self.updated_label = ctk.CTkLabel(
            self.scroll_container,
            text="Updated: --",
            font=ctk.CTkFont(size=10),
            text_color=TEXT_SECONDARY,
            anchor="w",
        )
        self.updated_label.grid(row=13, column=0, padx=12, pady=0, sticky="w")

    def load_task(self, task_id: int) -> None:
        """Fetch task details and populate fields.

        Args:
            task_id (int): Database identifier of task to display.
        """
        self._loading = True
        self.task_id = task_id

        task_record = self._db.get_task(task_id)
        if not task_record:
            logger.error("Failed to load task ID %d from database.", task_id)
            self._loading = False
            return

        task, matrix = task_record

        # Excerpt loading
        excerpt = self._db.get_transcript_excerpt_for_task(task_id)
        self.excerpt_box.configure(state="normal")
        self.excerpt_box.delete("1.0", "end")
        self.excerpt_box.insert("1.0", excerpt)
        self.excerpt_box.configure(state="disabled")

        # Populate Entries
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, task.title or "")

        self.notes_box.delete("1.0", "end")
        self.notes_box.insert("1.0", task.notes or "")

        self.due_date_entry.delete(0, "end")
        self.due_date_entry.insert(0, task.due_date or "")

        self.status_var.set(task.status)

        # Set Quadrant Display
        display_name = _QUADRANT_KEY_TO_DISPLAY.get(matrix.quadrant, "Schedule")
        self.quadrant_menu.set(display_name)

        # Set Timestamps
        created_str = self._format_timestamp(task.created_at)
        updated_str = self._format_timestamp(task.updated_at)
        self.created_label.configure(text=f"Created: {created_str}")
        self.updated_label.configure(text=f"Updated: {updated_str}")

        # Keep current copy for delta detection
        self._current_title = task.title or ""
        self._current_notes = task.notes or ""
        self._current_due_date = task.due_date or ""
        self._current_quadrant = matrix.quadrant or ""
        self._current_status = task.status

        self._loading = False

    def save_task(self) -> None:
        """Compare inputs with database, persisting modifications on difference."""
        if self._loading or self.task_id is None:
            return

        title = self.title_entry.get().strip()
        notes = self.notes_box.get("1.0", "end-1c").strip()
        due_date = self.due_date_entry.get().strip()
        status = self.status_var.get()

        # Check if anything changed
        title_changed = title != self._current_title
        notes_changed = notes != self._current_notes
        due_changed = due_date != self._current_due_date
        status_changed = status != self._current_status

        if title_changed or notes_changed or due_changed or status_changed:
            try:
                self._db.update_task(
                    task_id=self.task_id,
                    title=title,
                    notes=notes,
                    due_date=due_date,
                    status=status,
                )
                logger.info("Task ID %d updated successfully.", self.task_id)

                # Update delta check variables
                self._current_title = title
                self._current_notes = notes
                self._current_due_date = due_date
                self._current_status = status

                # Refresh timestamps (re-read task)
                task_record = self._db.get_task(self.task_id)
                if task_record:
                    updated_str = self._format_timestamp(task_record[0].updated_at)
                    self.updated_label.configure(text=f"Updated: {updated_str}")

                # Notify main window to redraw grids
                self.on_save()
            except Exception as e:
                logger.error("Failed to auto-save task ID %d: %s", self.task_id, e)

    def _on_quadrant_changed(self, value: str) -> None:
        """Handle option menu selection, triggering manual override immediately.

        Args:
            value (str): Text selected in OptionMenu list.
        """
        if self._loading or self.task_id is None:
            return

        target_quadrant = _QUADRANT_DISPLAY_TO_KEY.get(value, "schedule")
        if target_quadrant != self._current_quadrant:
            try:
                self._db.override_matrix_quadrant(self.task_id, target_quadrant)
                logger.info(
                    "Task ID %d quadrant overridden manually to '%s'.",
                    self.task_id,
                    target_quadrant,
                )
                self._current_quadrant = target_quadrant
                self.on_save()
            except Exception as e:
                logger.error("Failed to override matrix quadrant: %s", e)

    def close_panel(self) -> None:
        """Auto-save any pending changes and invoke the close event hook."""
        self.save_task()
        self.on_close()

    def _format_timestamp(self, ts_str: str | None) -> str:
        """Convert raw SQLite ISO timestamp string to user friendly readable text.

        Args:
            ts_str (str): Raw timestamp from database record.

        Returns:
            str: Reformatted human readable timestamp.
        """
        if not ts_str:
            return "--"
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%b %d, %H:%M")
        except ValueError:
            return ts_str
