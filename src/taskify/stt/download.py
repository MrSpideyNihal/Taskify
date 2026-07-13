"""Model downloader utilities for speech-to-text engines."""

import io
import zipfile
from pathlib import Path

import click
import httpx

from taskify.config import get_default_paths

# Catalog of known model download configurations
VOSK_MODEL_URLS = {
    "en-small": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "en-large": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgroup.zip",
    "de-small": "https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip",
    "fr-small": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
    "es-small": "https://alphacephei.com/vosk/models/vosk-model-small-es-0.3.zip",
}


def download_vosk_model(model_name: str) -> Path:
    """Download, extract, and position a Vosk speech model.

    Args:
        model_name (str): Identifier name from VOSK_MODEL_URLS catalog.

    Returns:
        Path: Target local model folder directory.

    Raises:
        ValueError: If model_name is not supported.
        RuntimeError: If download or extract fails.
    """
    if model_name not in VOSK_MODEL_URLS:
        raise ValueError(
            f"Vosk model '{model_name}' is not in the supported catalog. "
            f"Choose one of: {list(VOSK_MODEL_URLS.keys())}"
        )

    url = VOSK_MODEL_URLS[model_name]
    _, data_dir = get_default_paths()
    models_dir = data_dir / "models" / "vosk"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Derived directory name (e.g. 'vosk-model-small-en-us-0.15')
    archive_base_name = url.split("/")[-1].replace(".zip", "")
    target_model_path = models_dir / archive_base_name

    # Return immediately if model directory already exists
    if target_model_path.exists() and (target_model_path / "am").exists():
        return target_model_path

    click.echo(f"Downloading speech model '{model_name}' from: {url}")

    try:
        # Download zip archive into memory buffer
        buffer = io.BytesIO()
        with httpx.stream("GET", url, follow_redirects=True) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    f"HTTP response error {response.status_code} requesting model URL."
                )

            total_bytes = int(response.headers.get("content-length", 0))
            with click.progressbar(  # type: ignore[var-annotated]
                length=total_bytes, label="Downloading model archive..."
            ) as bar:
                for chunk in response.iter_bytes(chunk_size=8192):
                    buffer.write(chunk)
                    bar.update(len(chunk))

        # Reset buffer read marker
        buffer.seek(0)

        # Extract archive
        click.echo("Extracting model files...")
        with zipfile.ZipFile(buffer) as zip_ref:
            zip_ref.extractall(models_dir)

        # Confirm extraction folder existence
        if not target_model_path.exists():
            raise RuntimeError(
                f"Extracted folder '{target_model_path}' was not found. "
                "Archive extraction structure might be corrupted."
            )

        click.echo(f"Model successfully installed at: {target_model_path}")
        return target_model_path

    except Exception as e:
        # Clean folder in case of corrupt incomplete extractions
        if target_model_path.exists():
            import shutil

            shutil.rmtree(target_model_path, ignore_errors=True)
        raise RuntimeError(
            f"Failed to install speech model '{model_name}': {e}"
        ) from e
