"""Unit tests for the Taskify CLI."""

from click.testing import CliRunner
from taskify import __version__
from taskify.cli.main import main


def test_version_flag() -> None:
    """Test that the CLI version flag outputs the correct version."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert f"Taskify version {__version__}" in result.output


from unittest.mock import patch, MagicMock

def test_default_invocation() -> None:
    """Test that running taskify with no subcommands starts the GUI and scheduler."""
    runner = CliRunner()
    
    mock_db = MagicMock()
    mock_scheduler = MagicMock()
    mock_app = MagicMock()
    
    with patch("taskify.storage.database.DatabaseManager", return_value=mock_db), \
         patch("taskify.pipeline.scheduler.ExtractionScheduler", return_value=mock_scheduler), \
         patch("taskify.ui.main_window.MainWindow", return_value=mock_app):
         
        result = runner.invoke(main)
        
    assert result.exit_code == 0
    mock_scheduler.start.assert_called_once()
    mock_app.mainloop.assert_called_once()


def test_info_command() -> None:
    """Test that the info command outputs status information."""
    runner = CliRunner()
    result = runner.invoke(main, ["info"])
    assert result.exit_code == 0
    assert "Taskify System Information:" in result.output
    assert "Status: Initialized" in result.output
