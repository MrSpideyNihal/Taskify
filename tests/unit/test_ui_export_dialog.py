"""Unit tests for the ExportDialog GUI configuration component."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from taskify.ui.export_dialog import ExportDialog


@pytest.fixture
def mock_parent() -> MagicMock:
    """Fixture returning mock MainWindow parent."""
    parent = MagicMock()
    return parent


@pytest.fixture
def mock_db() -> MagicMock:
    """Fixture returning mock DatabaseManager."""
    db = MagicMock()
    return db


@pytest.fixture
def dialog(mock_parent: MagicMock, mock_db: MagicMock) -> ExportDialog:
    """Fixture returning instantiated ExportDialog."""
    return ExportDialog(mock_parent, mock_db)


def test_export_dialog_init(dialog: ExportDialog) -> None:
    """Test default state of ExportDialog controls."""
    assert dialog.format_var.get() == "Markdown (.md)"
    assert dialog.quad_var.get() == "All Quadrants"
    assert dialog.date_filter_enabled.get() is False
    assert dialog.start_date_entry.cget("state") == "disabled"
    assert dialog.end_date_entry.cget("state") == "disabled"


def test_toggle_date_inputs(dialog: ExportDialog) -> None:
    """Test checkbox command enables/disables date fields."""
    # Enable
    dialog.date_filter_enabled.set(True)
    dialog.toggle_date_inputs()
    assert dialog.start_date_entry.cget("state") == "normal"
    assert dialog.end_date_entry.cget("state") == "normal"

    # Disable
    dialog.date_filter_enabled.set(False)
    dialog.toggle_date_inputs()
    assert dialog.start_date_entry.cget("state") == "disabled"
    assert dialog.end_date_entry.cget("state") == "disabled"


@patch("tkinter.messagebox.showerror")
def test_date_validations_missing_dates(mock_error: MagicMock, dialog: ExportDialog) -> None:
    """Test validation errors if date filter enabled but fields empty."""
    dialog.date_filter_enabled.set(True)
    dialog.toggle_date_inputs()

    dialog.start_date_entry.delete(0, "end")
    dialog.end_date_entry.delete(0, "end")

    dialog.perform_export()
    mock_error.assert_called_with("Validation Error", "Start and End dates are required when date filtering is active.")


@patch("tkinter.messagebox.showerror")
def test_date_validations_invalid_start_format(mock_error: MagicMock, dialog: ExportDialog) -> None:
    """Test validation error for malformed start date format."""
    dialog.date_filter_enabled.set(True)
    dialog.toggle_date_inputs()

    dialog.start_date_entry.insert(0, "01/01/2026")
    dialog.end_date_entry.insert(0, "2026-07-18")

    dialog.perform_export()
    mock_error.assert_called_with("Validation Error", "Start date must match format: YYYY-MM-DD (e.g. 2026-07-01)")


@patch("tkinter.messagebox.showerror")
def test_date_validations_invalid_end_format(mock_error: MagicMock, dialog: ExportDialog) -> None:
    """Test validation error for malformed end date format."""
    dialog.date_filter_enabled.set(True)
    dialog.toggle_date_inputs()

    dialog.start_date_entry.insert(0, "2026-07-01")
    dialog.end_date_entry.delete(0, "end")
    dialog.end_date_entry.insert(0, "2026-07-invalid")

    dialog.perform_export()
    mock_error.assert_called_with("Validation Error", "End date must match format: YYYY-MM-DD (e.g. 2026-07-18)")


@patch("tkinter.messagebox.showerror")
def test_date_validations_chronology(mock_error: MagicMock, dialog: ExportDialog) -> None:
    """Test validation error if start date exceeds end date."""
    dialog.date_filter_enabled.set(True)
    dialog.toggle_date_inputs()

    dialog.start_date_entry.insert(0, "2026-07-18")
    dialog.end_date_entry.delete(0, "end")
    dialog.end_date_entry.insert(0, "2026-07-01")

    dialog.perform_export()
    mock_error.assert_called_with("Validation Error", "Start date cannot exceed End date.")


@patch("tkinter.filedialog.asksaveasfilename")
@patch("taskify.ui.export_dialog.export_tasks_to_file")
@patch("tkinter.messagebox.showinfo")
def test_successful_export_markdown(
    mock_info: MagicMock,
    mock_export_fn: MagicMock,
    mock_file_dialog: MagicMock,
    dialog: ExportDialog,
) -> None:
    """Test successful Markdown export calls filesystem serializer."""
    mock_file_dialog.return_value = "/dummy/path/export.md"
    mock_export_fn.return_value = 5

    dialog.format_var.set("Markdown (.md)")
    dialog.quad_var.set("Do First")

    dialog.perform_export()

    mock_export_fn.assert_called_once_with(
        db=dialog.db,
        filepath=Path("/dummy/path/export.md"),
        format="markdown",
        quadrant="do_first",
        start_date=None,
        end_date=None,
    )
    mock_info.assert_called_with("Export Successful", "Successfully exported 5 tasks to:\nexport.md")


@patch("tkinter.filedialog.asksaveasfilename")
@patch("taskify.ui.export_dialog.export_tasks_to_file")
@patch("tkinter.messagebox.showinfo")
def test_successful_export_json(
    mock_info: MagicMock,
    mock_export_fn: MagicMock,
    mock_file_dialog: MagicMock,
    dialog: ExportDialog,
) -> None:
    """Test successful JSON export calls filesystem serializer."""
    mock_file_dialog.return_value = "/dummy/path/export.json"
    mock_export_fn.return_value = 10

    dialog.format_var.set("JSON (.json)")
    dialog.quad_var.set("All Quadrants")

    dialog.perform_export()

    mock_export_fn.assert_called_once_with(
        db=dialog.db,
        filepath=Path("/dummy/path/export.json"),
        format="json",
        quadrant=None,
        start_date=None,
        end_date=None,
    )
    mock_info.assert_called_with("Export Successful", "Successfully exported 10 tasks to:\nexport.json")
