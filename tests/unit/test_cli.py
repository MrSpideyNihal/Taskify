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


def test_default_invocation() -> None:
    """Test that running taskify with no subcommands prints the GUI launch status."""
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
    assert "Starting Taskify GUI..." in result.output
    assert "GUI placeholder launched successfully." in result.output


def test_info_command() -> None:
    """Test that the info command outputs status information."""
    runner = CliRunner()
    result = runner.invoke(main, ["info"])
    assert result.exit_code == 0
    assert "Taskify System Information:" in result.output
    assert "Status: Initialized" in result.output
