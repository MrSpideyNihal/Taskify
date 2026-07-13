"""Command Line Interface for Taskify."""

import click

from taskify import __version__


@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Show application version.")
@click.pass_context
def main(ctx: click.Context, version: bool) -> None:
    """Taskify: A fully offline, privacy-first, voice-driven task manager."""
    if version:
        click.echo(f"Taskify version {__version__}")
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo("Starting Taskify GUI...")
        # GUI import and launch will go here in future issues.
        # For now, print a success message and exit.
        click.echo("GUI placeholder launched successfully.")
        ctx.exit(0)


@main.command()
def info() -> None:
    """Show details about local system paths and configuration."""
    click.echo("Taskify System Information:")
    click.echo("Status: Initialized")
