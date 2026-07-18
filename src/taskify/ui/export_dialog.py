"""Modal export dialog window supporting Markdown and JSON file exports."""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from taskify.export.exporter import export_tasks_to_file

if TYPE_CHECKING:
    from taskify.storage.database import DatabaseManager
    from taskify.ui.main_window import MainWindow

logger = logging.getLogger(__name__)

# Aesthetic styling variables matching theme
BG_COLOR = "#121214"
CARD_BG = "#1A1A1E"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#9999A1"
BORDER_COLOR = "#2D2D34"
ACCENT_BLUE = "#5F9FFF"
ACCENT_GREEN = "#4ADE80"


class ExportDialog(ctk.CTkToplevel):
    """Modal dialog managing task filter choices and triggering exports."""

    def __init__(self, parent: MainWindow, db: DatabaseManager) -> None:
        """Initialize export configuration window.

        Args:
            parent (MainWindow): Main application dashboard window.
            db (DatabaseManager): Open SQLite database connection manager.
        """
        super().__init__(parent)
        self.parent = parent
        self.db = db

        self.title("Export Tasks Checklist")
        self.geometry("450x420")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)

        # Make modal
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        # Keyboard ESC binder to cancel
        self.bind("<Escape>", lambda e: self.destroy())

        # Grid config
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # Main settings container frame
        self.main_frame = ctk.CTkFrame(
            self,
            fg_color=CARD_BG,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=12,
        )
        self.main_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="nsew")
        self.main_frame.grid_columnconfigure(1, weight=1)

        # Title Label
        title_lbl = ctk.CTkLabel(
            self.main_frame,
            text="EXPORT CONFIGURATION",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        title_lbl.grid(
            row=0, column=0, columnspan=2, padx=20, pady=(20, 16), sticky="w"
        )

        # 1. Format Selection
        format_lbl = ctk.CTkLabel(
            self.main_frame, text="File Format:", text_color=TEXT_SECONDARY
        )
        format_lbl.grid(row=1, column=0, padx=20, pady=8, sticky="w")
        self.format_var = tk.StringVar(value="Markdown (.md)")
        self.format_menu = ctk.CTkOptionMenu(
            self.main_frame,
            values=["Markdown (.md)", "JSON (.json)"],
            variable=self.format_var,
            fg_color=BG_COLOR,
            button_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=CARD_BG,
        )
        self.format_menu.grid(row=1, column=1, padx=20, pady=8, sticky="ew")

        # 2. Quadrant Filter Selection
        quad_lbl = ctk.CTkLabel(
            self.main_frame, text="Quadrant Filter:", text_color=TEXT_SECONDARY
        )
        quad_lbl.grid(row=2, column=0, padx=20, pady=8, sticky="w")
        self.quad_var = tk.StringVar(value="All Quadrants")
        self.quad_menu = ctk.CTkOptionMenu(
            self.main_frame,
            values=["All Quadrants", "Do First", "Schedule", "Delegate", "Eliminate"],
            variable=self.quad_var,
            fg_color=BG_COLOR,
            button_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            dropdown_fg_color=CARD_BG,
        )
        self.quad_menu.grid(row=2, column=1, padx=20, pady=8, sticky="ew")

        # Separator Frame
        sep = ctk.CTkFrame(self.main_frame, height=1, fg_color=BORDER_COLOR)
        sep.grid(row=3, column=0, columnspan=2, padx=16, pady=12, sticky="ew")

        # 3. Date range filters
        self.date_filter_enabled = tk.BooleanVar(value=False)
        self.date_checkbox = ctk.CTkCheckBox(
            self.main_frame,
            text="Filter by Date Range",
            variable=self.date_filter_enabled,
            command=self.toggle_date_inputs,
            text_color=TEXT_PRIMARY,
            fg_color=ACCENT_BLUE,
            hover_color="#4F8FEE",
        )
        self.date_checkbox.grid(
            row=4, column=0, columnspan=2, padx=20, pady=6, sticky="w"
        )

        # Start Date Row
        start_lbl = ctk.CTkLabel(
            self.main_frame, text="Start Date (YYYY-MM-DD):", text_color=TEXT_SECONDARY
        )
        start_lbl.grid(row=5, column=0, padx=20, pady=6, sticky="w")
        self.start_date_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="e.g. 2026-07-01",
            fg_color=BG_COLOR,
            border_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            state="disabled",
        )
        self.start_date_entry.grid(row=5, column=1, padx=20, pady=6, sticky="ew")

        # End Date Row
        end_lbl = ctk.CTkLabel(
            self.main_frame, text="End Date (YYYY-MM-DD):", text_color=TEXT_SECONDARY
        )
        end_lbl.grid(row=6, column=0, padx=20, pady=6, sticky="w")
        self.end_date_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="e.g. 2026-07-18",
            fg_color=BG_COLOR,
            border_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            state="disabled",
        )
        self.end_date_entry.grid(row=6, column=1, padx=20, pady=6, sticky="ew")

        # Bottom Buttons Frame
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, padx=16, pady=(8, 16), sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent",
            hover_color=CARD_BG,
            text_color=TEXT_SECONDARY,
            border_color=BORDER_COLOR,
            border_width=1,
            command=self.destroy,
        )
        self.cancel_btn.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="ew")

        self.export_btn = ctk.CTkButton(
            btn_frame,
            text="Export Tasks",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT_GREEN,
            hover_color="#22C55E",
            text_color="#000000",
            command=self.perform_export,
        )
        self.export_btn.grid(row=0, column=1, padx=(8, 0), pady=4, sticky="ew")

        # Pre-populate date templates
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.end_date_entry.insert(0, today_str)

    def toggle_date_inputs(self) -> None:
        """Enable or disable date entries depending on checkbox selection state."""
        if self.date_filter_enabled.get():
            self.start_date_entry.configure(state="normal")
            self.end_date_entry.configure(state="normal")
        else:
            self.start_date_entry.configure(state="disabled")
            self.end_date_entry.configure(state="disabled")

    def perform_export(self) -> None:
        """Validate input values, request output path from user, and serialize files."""
        # 1. Date Range Validations
        start_dt = None
        end_dt = None

        if self.date_filter_enabled.get():
            start_str = self.start_date_entry.get().strip()
            end_str = self.end_date_entry.get().strip()

            if not start_str or not end_str:
                messagebox.showerror(
                    "Validation Error",
                    "Start and End dates are required when date filtering is active.",
                )
                return

            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror(
                    "Validation Error",
                    "Start date must match format: YYYY-MM-DD (e.g. 2026-07-01)",
                )
                return

            try:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d")
                # Clamp end date to end of day to include all entries on that date
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
            except ValueError:
                messagebox.showerror(
                    "Validation Error",
                    "End date must match format: YYYY-MM-DD (e.g. 2026-07-18)",
                )
                return

            if start_dt > end_dt:
                messagebox.showerror(
                    "Validation Error", "Start date cannot exceed End date."
                )
                return

        # 2. Quadrant Filter
        quad_choice = self.quad_var.get()
        quad_val = None
        if quad_choice == "Do First":
            quad_val = "do_first"
        elif quad_choice == "Schedule":
            quad_val = "schedule"
        elif quad_choice == "Delegate":
            quad_val = "delegate"
        elif quad_choice == "Eliminate":
            quad_val = "eliminate"

        # 3. Format & Default File Dialog setup
        fmt_choice = self.format_var.get()
        if "Markdown" in fmt_choice:
            fmt_val = "markdown"
            ext = ".md"
            types = [("Markdown checklist", "*.md"), ("All files", "*.*")]
        else:
            fmt_val = "json"
            ext = ".json"
            types = [("JSON export", "*.json"), ("All files", "*.*")]

        # Show Save As file dialog
        initial_file = f"taskify_export_{datetime.now().strftime('%Y%m%d')}{ext}"
        filepath_str = filedialog.asksaveasfilename(
            parent=self,
            title="Save Export File",
            initialfile=initial_file,
            defaultextension=ext,
            filetypes=types,
        )

        if not filepath_str:
            return  # user cancelled the file selection dialog

        filepath = Path(filepath_str)

        try:
            # Trigger serialization
            count = export_tasks_to_file(
                db=self.db,
                filepath=filepath,
                format=fmt_val,
                quadrant=quad_val,
                start_date=start_dt,
                end_date=end_dt,
            )
            msg = f"Successfully exported {count} tasks to:\n{filepath.name}"
            messagebox.showinfo("Export Successful", msg)
            self.destroy()
        except Exception as exc:
            logger.error("Failed to write tasks export: %s", exc)
            err_msg = f"An error occurred while exporting: {exc}"
            messagebox.showerror("Export Error", err_msg)
