"""Main application window featuring the Eisenhower Matrix dashboard."""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime
from typing import TYPE_CHECKING

import customtkinter as ctk

from taskify.llm.models import MatrixQuadrant
from taskify.pipeline.scheduler import EVENT_TASKS_UPDATED

if TYPE_CHECKING:
    from taskify.config import Settings
    from taskify.pipeline.scheduler import EventBus
    from taskify.storage.database import DatabaseManager
    from taskify.storage.models import TaskRecord

logger = logging.getLogger(__name__)

# Premium color palette matching modern HSL design guidelines
BG_COLOR = "#121214"
CARD_BG = "#1A1A1E"
CARD_HOVER = "#24242A"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#9999A1"
BORDER_COLOR = "#2D2D34"

# Quadrant specific accent colors
COLOR_DO_FIRST = "#FF5F5F"  # Vibrant Coral Red
COLOR_SCHEDULE = "#5F9FFF"  # Clean Sky Blue
COLOR_DELEGATE = "#FFBF5F"  # Warm Orange/Amber
COLOR_ELIMINATE = "#8A8A93"  # Muted Slate Gray


class TaskCard(ctk.CTkFrame):
    """Interactive visual card presenting a single task."""

    def __init__(
        self,
        master: ctk.CTkScrollableFrame,
        task: TaskRecord,
        on_action: ctk.Callable[[str, int], None],
    ) -> None:
        """Initialize task card.

        Args:
            master (CTkScrollableFrame): Parent container.
            task (TaskRecord): Underlying database task record.
            on_action (Callable): Callback with action name and task_id.
        """
        super().__init__(
            master,
            fg_color=CARD_BG,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=8,
        )
        self.task = task
        self.task_id = task.id
        self.on_action = on_action

        # Layout settings
        self.grid_columnconfigure(0, weight=1)

        # Title (Bold, prominent)
        self.title_label = ctk.CTkLabel(
            self,
            text=task.title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.title_label.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        # Subtitle / Snippet from transcript or notes
        notes_snippet = task.notes.strip() if task.notes else ""
        if notes_snippet:
            self.notes_label = ctk.CTkLabel(
                self,
                text=notes_snippet,
                font=ctk.CTkFont(size=12),
                text_color=TEXT_SECONDARY,
                anchor="w",
                justify="left",
                wraplength=380,
            )
            self.notes_label.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="w")

        # Footer (Due date and timestamp)
        footer_parts = []
        if task.due_date:
            footer_parts.append(f"Due: {task.due_date}")
        if task.created_at:
            try:
                # Format SQLite UTC timestamp to user friendly format
                dt = datetime.strptime(task.created_at, "%Y-%m-%d %H:%M:%S")
                footer_parts.append(dt.strftime("%b %d, %H:%M"))
            except ValueError:
                footer_parts.append(task.created_at)

        footer_text = " • ".join(footer_parts)
        if footer_text:
            self.footer_label = ctk.CTkLabel(
                self,
                text=footer_text,
                font=ctk.CTkFont(size=11),
                text_color=TEXT_SECONDARY,
                anchor="w",
            )
            self.footer_label.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="w")

        # Bind hover events for interactive feel
        for widget in (self, self.title_label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-3>", self._show_context_menu)
            widget.bind("<Button-2>", self._show_context_menu)  # macOS right click

        if notes_snippet:
            self.notes_label.bind("<Enter>", self._on_enter)
            self.notes_label.bind("<Leave>", self._on_leave)
            self.notes_label.bind("<Button-3>", self._show_context_menu)
            self.notes_label.bind("<Button-2>", self._show_context_menu)

        if footer_text:
            self.footer_label.bind("<Enter>", self._on_enter)
            self.footer_label.bind("<Leave>", self._on_leave)
            self.footer_label.bind("<Button-3>", self._show_context_menu)
            self.footer_label.bind("<Button-2>", self._show_context_menu)

    def _on_enter(self, event: tk.Event) -> None:
        self.configure(fg_color=CARD_HOVER)

    def _on_leave(self, event: tk.Event) -> None:
        self.configure(fg_color=CARD_BG)

    def _show_context_menu(self, event: tk.Event) -> None:
        if self.task_id is None:
            return

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            activebackground=CARD_HOVER,
        )
        # Actions
        menu.add_command(
            label="✓ Mark Done",
            command=lambda: self.on_action("complete", self.task_id),
        )
        menu.add_separator()

        # Move sub-menu
        move_menu = tk.Menu(
            menu,
            tearoff=0,
            bg=CARD_BG,
            fg=TEXT_PRIMARY,
            activebackground=CARD_HOVER,
        )
        move_menu.add_command(
            label="1. Do First",
            command=lambda: self.on_action("move_do_first", self.task_id),
        )
        move_menu.add_command(
            label="2. Schedule",
            command=lambda: self.on_action("move_schedule", self.task_id),
        )
        move_menu.add_command(
            label="3. Delegate",
            command=lambda: self.on_action("move_delegate", self.task_id),
        )
        move_menu.add_command(
            label="4. Eliminate",
            command=lambda: self.on_action("move_eliminate", self.task_id),
        )
        menu.add_cascade(label="→ Move Quadrant", menu=move_menu)
        menu.add_separator()

        menu.add_command(
            label="✗ Delete Task",
            command=lambda: self.on_action("delete", self.task_id),
        )

        # Render popup
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


class MainWindow(ctk.CTk):
    """Main desktop user interface window using CustomTkinter."""

    def __init__(
        self,
        db: DatabaseManager,
        settings: Settings,
        bus: EventBus,
    ) -> None:
        """Initialize the main application dashboard.

        Args:
            db (DatabaseManager): Open database manager.
            settings (Settings): Active application settings.
            bus (EventBus): Pub/Sub event bus.
        """
        super().__init__()
        self._db = db
        self._settings = settings
        self._bus = bus

        # Main window configuration
        self.title("Taskify - Eisenhower Matrix Dashboard")
        self.geometry("1080x780")
        self.minsize(900, 650)
        self.configure(fg_color=BG_COLOR)

        # Style configurations
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Responsive main grid layout configuration
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)  # Status Bar
        self.grid_columnconfigure(0, weight=1)

        # Container for the 2x2 quadrant layout
        self.matrix_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.matrix_frame.grid(row=0, column=0, padx=16, pady=16, sticky="nsew")

        self.matrix_frame.grid_rowconfigure(0, weight=1)
        self.matrix_frame.grid_rowconfigure(1, weight=1)
        self.matrix_frame.grid_columnconfigure(0, weight=1)
        self.matrix_frame.grid_columnconfigure(1, weight=1)

        # Initialize quadrants
        self.quadrants: dict[str, ctk.CTkScrollableFrame] = {}
        self._create_quadrant(
            "Do First",
            "Urgent & Important",
            COLOR_DO_FIRST,
            0,
            0,
            MatrixQuadrant.DO_FIRST.value,
        )
        self._create_quadrant(
            "Schedule",
            "Not Urgent & Important",
            COLOR_SCHEDULE,
            0,
            1,
            MatrixQuadrant.SCHEDULE.value,
        )
        self._create_quadrant(
            "Delegate",
            "Urgent & Not Important",
            COLOR_DELEGATE,
            1,
            0,
            MatrixQuadrant.DELEGATE.value,
        )
        self._create_quadrant(
            "Eliminate",
            "Not Urgent & Not Important",
            COLOR_ELIMINATE,
            1,
            1,
            MatrixQuadrant.ELIMINATE.value,
        )

        # Create Status Bar
        self._create_status_bar()

        # Initial data loading
        self.refresh_all_quadrants()

        # Wire EventBus triggers thread-safely
        self._bus.subscribe(EVENT_TASKS_UPDATED, self._on_tasks_updated)

    def _create_quadrant(
        self,
        title: str,
        subtitle: str,
        accent_color: str,
        row: int,
        col: int,
        quadrant_key: str,
    ) -> None:
        """Construct a single quadrant framework widget."""
        frame = ctk.CTkFrame(
            self.matrix_frame,
            fg_color=CARD_BG,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=12,
        )
        frame.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Header section
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")

        indicator = ctk.CTkLabel(
            header_frame,
            text="■",
            text_color=accent_color,
            font=ctk.CTkFont(size=18),
        )
        indicator.pack(side="left", padx=(0, 6))

        title_label = ctk.CTkLabel(
            header_frame,
            text=title.upper(),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title_label.pack(side="left")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text=f" ({subtitle})",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SECONDARY,
        )
        subtitle_label.pack(side="left")

        # Scrollable area for cards
        scroll_frame = ctk.CTkScrollableFrame(
            frame,
            fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=CARD_HOVER,
        )
        scroll_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self.quadrants[quadrant_key] = scroll_frame

    def _create_status_bar(self) -> None:
        """Construct the application status bar frame."""
        self.status_bar = ctk.CTkFrame(
            self,
            height=32,
            fg_color=CARD_BG,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=0,
        )
        self.status_bar.grid(row=1, column=0, sticky="ew")

        # Left: STT Engine & Model details
        if self._settings.stt.engine == "vosk":
            model_info = self._settings.stt.vosk_model
        else:
            model_info = self._settings.stt.whisper_model
        stt_info = f"STT: {self._settings.stt.engine.upper()} ({model_info})"
        self.stt_label = ctk.CTkLabel(
            self.status_bar,
            text=stt_info,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SECONDARY,
        )
        self.stt_label.pack(side="left", padx=16, pady=4)

        # Center Left: LLM backend
        llm_info = f"LLM Backend: {self._settings.llm.backend.upper()}"
        self.llm_label = ctk.CTkLabel(
            self.status_bar,
            text=llm_info,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SECONDARY,
        )
        self.llm_label.pack(side="left", padx=16, pady=4)

        # Right: Last updated time
        self.time_label = ctk.CTkLabel(
            self.status_bar,
            text="Last Extraction: Never",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SECONDARY,
        )
        self.time_label.pack(side="right", padx=16, pady=4)

        # Center Right: Recording state
        self.state_label = ctk.CTkLabel(
            self.status_bar,
            text="● Idle",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_SECONDARY,
        )
        self.state_label.pack(side="right", padx=16, pady=4)

    def refresh_all_quadrants(self) -> None:
        """Query task database and render update matrices safely."""
        for quadrant_key, scroll_frame in self.quadrants.items():
            # Clear previous widgets
            for child in scroll_frame.winfo_children():
                child.destroy()

            # Retrieve active tasks (filter out completed ones)
            task_tuples = self._db.get_tasks_in_quadrant(quadrant_key)
            row_idx = 0
            for task, _ in task_tuples:
                if task.status == "completed":
                    continue

                card = TaskCard(scroll_frame, task, self.handle_task_action)
                card.grid(row=row_idx, column=0, padx=4, pady=4, sticky="ew")
                scroll_frame.grid_columnconfigure(0, weight=1)
                row_idx += 1

    def handle_task_action(self, action: str, task_id: int) -> None:
        """Handle context menu action callbacks.

        Args:
            action (str): Identifier of click action.
            task_id (int): Primary key of target task record.
        """
        try:
            if action == "complete":
                # Retrieve the current task to preserve all its fields
                task_data = self._db.get_task(task_id)
                if task_data:
                    task, _ = task_data
                    self._db.update_task(
                        task_id=task_id,
                        title=task.title,
                        notes=task.notes,
                        due_date=task.due_date,
                        status="completed",
                    )
            elif action == "delete":
                self._db.delete_task(task_id)
            elif action.startswith("move_"):
                quadrant_name = action.replace("move_", "")
                self._db.override_matrix_quadrant(task_id, quadrant_name)

            # Trigger a refresh of the dashboard
            self.refresh_all_quadrants()
            logger.info("Successfully executed %s on task %d", action, task_id)
        except Exception as e:
            logger.error("Failed executing task action %s: %s", action, e)

    def _on_tasks_updated(self, data: object) -> None:
        """Handle background thread task updates safely on the Tkinter thread."""
        now_str = datetime.now().strftime("%H:%M:%S")
        self.after(
            0,
            lambda: self.time_label.configure(text=f"Last Extraction: {now_str}"),
        )
        self.after(0, self.refresh_all_quadrants)
