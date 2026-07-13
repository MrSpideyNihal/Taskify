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
    from taskify.config import get_default_paths
    config_dir, data_dir = get_default_paths()
    click.echo("Taskify System Information:")
    click.echo("Status: Initialized")
    click.echo(f"Default Config Directory: {config_dir}")
    click.echo(f"Default Data Directory: {data_dir}")


@main.group()
def config() -> None:
    """Manage application configuration."""
    pass


@config.command(name="init")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force overwrite existing configuration file.",
)
def config_init(force: bool) -> None:
    """Initialize default user configuration file."""
    try:
        from taskify.config import initialize_user_config

        path = initialize_user_config(force=force)
        click.echo(f"Configuration file initialized: {path}")
    except Exception as e:
        click.echo(f"Error initializing configuration: {e}", err=True)


@config.command(name="show")
def config_show() -> None:
    """Display merged configuration details."""
    try:
        from taskify.config import load_settings

        settings = load_settings()
        click.echo(
            f"Config File: {settings.config_path or 'Not initialized (using defaults)'}"
        )
        click.echo("---")
        click.echo(
            f"[audio]\n"
            f"device = {settings.audio.device}\n"
            f"sample_rate = {settings.audio.sample_rate}\n"
            f"chunk_duration_ms = {settings.audio.chunk_duration_ms}\n"
            f"silence_threshold = {settings.audio.silence_threshold}\n"
            f"silence_duration_s = {settings.audio.silence_duration_s}"
        )
        click.echo(
            f"\n[stt]\n"
            f"engine = {settings.stt.engine}\n"
            f"vosk_model = {settings.stt.vosk_model}\n"
            f"whisper_model = {settings.stt.whisper_model}\n"
            f"language = {settings.stt.language}"
        )
        click.echo(
            f"\n[llm]\n"
            f"backend = {settings.llm.backend}\n"
            f"ollama_host = {settings.llm.ollama_host}\n"
            f"ollama_model = {settings.llm.ollama_model}\n"
            f"extraction_interval_s = {settings.llm.extraction_interval_s}"
        )
        click.echo(
            f"\n[storage]\n"
            f"data_dir = {settings.storage.data_dir}\n"
            f"log_dir = {settings.storage.log_dir}"
        )
        click.echo(
            f"\n[logging]\n"
            f"level = {settings.logging.level}\n"
            f"debug_llm = {settings.logging.debug_llm}"
        )
    except Exception as e:
        click.echo(f"Error reading configuration: {e}", err=True)


@main.command(name="download-model")
@click.option(
    "--engine",
    "-e",
    type=click.Choice(["vosk", "whisper"]),
    default="vosk",
    help="Target STT engine.",
)
@click.option(
    "--lang",
    "-l",
    default="en",
    help="Language code (BCP-47) for default mapping.",
)
@click.option(
    "--size",
    "-s",
    type=click.Choice(["small", "large"]),
    default="small",
    help="Model size for default mapping.",
)
@click.option(
    "--model",
    "-m",
    default=None,
    help="Explicit model name override.",
)
def download_model(
    engine: str, lang: str, size: str, model: str | None
) -> None:
    """Download local speech-to-text models."""
    model_id = model if model else f"{lang}-{size}".lower()

    if engine == "vosk":
        try:
            from taskify.stt import download_vosk_model

            path = download_vosk_model(model_id)
            click.echo(f"Vosk model ready at: {path}")
        except Exception as e:
            click.echo(f"Error downloading Vosk model: {e}", err=True)
            raise click.Abort() from e
    elif engine == "whisper":
        click.echo(
            "Whisper engine is not yet implemented. Cannot download Whisper models.",
            err=True,
        )
        raise click.Abort()


