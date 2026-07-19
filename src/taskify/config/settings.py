"""Configuration settings management and schema validation for Taskify."""

import importlib.resources
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self


@dataclass
class AudioSettings:
    """Settings for microphone audio capture."""

    device: str
    sample_rate: int
    chunk_duration_ms: int
    silence_threshold: float
    silence_duration_s: float

    def validate(self) -> None:
        """Validate audio configuration parameters."""
        if self.sample_rate <= 0:
            raise ValueError("audio.sample_rate must be a positive integer.")
        if self.chunk_duration_ms <= 0:
            raise ValueError("audio.chunk_duration_ms must be a positive integer.")
        if self.silence_threshold < 0.0 or self.silence_threshold > 1.0:
            raise ValueError("audio.silence_threshold must be between 0.0 and 1.0.")
        if self.silence_duration_s <= 0.0:
            raise ValueError("audio.silence_duration_s must be a positive number.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create class instance from dictionary parsing types safely."""
        return cls(
            device=str(data.get("device", "default")),
            sample_rate=int(data.get("sample_rate", 16000)),
            chunk_duration_ms=int(data.get("chunk_duration_ms", 200)),
            silence_threshold=float(data.get("silence_threshold", 0.01)),
            silence_duration_s=float(data.get("silence_duration_s", 1.5)),
        )


@dataclass
class STTSettings:
    """Settings for local speech-to-text engines."""

    engine: str
    vosk_model: str
    whisper_model: str
    language: str

    def validate(self) -> None:
        """Validate speech-to-text configuration parameters."""
        if self.engine not in ("vosk", "whisper"):
            raise ValueError("stt.engine must be either 'vosk' or 'whisper'.")
        if not self.vosk_model.strip():
            raise ValueError("stt.vosk_model must not be empty.")
        if not self.whisper_model.strip():
            raise ValueError("stt.whisper_model must not be empty.")
        if not self.language.strip():
            raise ValueError("stt.language must not be empty.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create class instance from dictionary parsing types safely."""
        return cls(
            engine=str(data.get("engine", "vosk")),
            vosk_model=str(data.get("vosk_model", "en-small")),
            whisper_model=str(data.get("whisper_model", "base")),
            language=str(data.get("language", "en")),
        )


@dataclass
class LLMSettings:
    """Settings for task extraction and classification LLM/NLP models."""

    backend: str
    ollama_host: str
    ollama_model: str
    extraction_interval_s: int

    def validate(self) -> None:
        """Validate LLM configuration parameters."""
        if self.backend not in ("ollama", "nlp"):
            raise ValueError("llm.backend must be either 'ollama' or 'nlp'.")
        if not self.ollama_host.strip():
            raise ValueError("llm.ollama_host must not be empty.")
        if not self.ollama_model.strip():
            raise ValueError("llm.ollama_model must not be empty.")
        if self.extraction_interval_s <= 0:
            raise ValueError("llm.extraction_interval_s must be a positive integer.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create class instance from dictionary parsing types safely."""
        return cls(
            backend=str(data.get("backend", "ollama")),
            ollama_host=str(data.get("ollama_host", "http://localhost:11434")),
            ollama_model=str(data.get("ollama_model", "phi4-mini")),
            extraction_interval_s=int(data.get("extraction_interval_s", 300)),
        )


@dataclass
class StorageSettings:
    """Settings for SQLite database and rotating logs path configurations."""

    data_dir: Path
    log_dir: Path

    def validate(self) -> None:
        """Validate paths configuration."""
        # Paths validation will occur when directory creations are attempted.
        pass

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_data_dir: Path) -> Self:
        """Create class instance from dictionary parsing paths safely."""
        data_dir_str = data.get("data_dir", "")
        data_dir = Path(data_dir_str) if data_dir_str else default_data_dir

        log_dir_str = data.get("log_dir", "")
        log_dir = Path(log_dir_str) if log_dir_str else data_dir / "logs"

        return cls(data_dir=data_dir, log_dir=log_dir)


@dataclass
class LoggingSettings:
    """Settings for console and file logger configurations."""

    level: str
    debug_llm: bool

    def validate(self) -> None:
        """Validate logging parameters."""
        valid_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        if self.level.upper() not in valid_levels:
            raise ValueError(f"logging.level must be one of {valid_levels}.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create class instance from dictionary parsing types safely."""
        return cls(
            level=str(data.get("level", "INFO")).upper(),
            debug_llm=bool(data.get("debug_llm", False)),
        )


@dataclass
class Settings:
    """Consolidated configuration settings for Taskify."""

    audio: AudioSettings
    stt: STTSettings
    llm: LLMSettings
    storage: StorageSettings
    logging: LoggingSettings
    config_path: Path | None = None

    def validate(self) -> None:
        """Run validation checks on all settings sections."""
        self.audio.validate()
        self.stt.validate()
        self.llm.validate()
        self.storage.validate()
        self.logging.validate()


def get_default_paths() -> tuple[Path, Path]:
    """Retrieve default cross-platform paths for configuration and data directories.

    Returns:
        tuple[Path, Path]: (config_dir_path, data_dir_path)
    """
    home = Path.home()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        localappdata = os.environ.get("LOCALAPPDATA")
        config_dir = (
            Path(appdata) / "Taskify"
            if appdata
            else home / "AppData" / "Roaming" / "Taskify"
        )
        data_dir = (
            Path(localappdata) / "Taskify"
            if localappdata
            else home / "AppData" / "Local" / "Taskify"
        )
    elif sys.platform == "darwin":
        support = home / "Library" / "Application Support" / "Taskify"
        config_dir = support
        data_dir = support
    else:  # linux and others
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        xdg_data = os.environ.get("XDG_DATA_HOME")
        config_dir = (
            Path(xdg_config) / "taskify" if xdg_config else home / ".config" / "taskify"
        )
        data_dir = (
            Path(xdg_data) / "taskify"
            if xdg_data
            else home / ".local" / "share" / "taskify"
        )

    return config_dir, data_dir


def load_default_config_text() -> str:
    """Read the default configuration template from packaged resources.

    Returns:
        str: Configuration template content.
    """
    ref = importlib.resources.files("taskify.config").joinpath("config.default.toml")
    return ref.read_text(encoding="utf-8")


def merge_dicts(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge custom user parameters over default configuration dictionary.

    Args:
        default (dict): Pinned default configuration layout.
        override (dict): Custom override dictionary.

    Returns:
        dict: Merged configuration layout.
    """
    result = default.copy()
    for k, v in override.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = merge_dicts(result[k], v)
        else:
            result[k] = v
    return result


def load_settings(user_config_path: Path | None = None) -> Settings:
    """Load, merge, and validate configurations from defaults and overrides.

    Args:
        user_config_path (Path, optional): Custom path to configuration override.

    Returns:
        Settings: Validated configurations.
    """
    # 1. Load packaged default config
    default_text = load_default_config_text()
    default_dict = tomllib.loads(default_text)

    # 2. Determine target config locations
    config_dir, default_data_dir = get_default_paths()
    target_config = user_config_path if user_config_path else config_dir / "config.toml"

    # 3. Load user overrides if present
    override_dict: dict[str, Any] = {}
    if target_config.exists() and target_config.is_file():
        try:
            with open(target_config, "rb") as f:
                override_dict = tomllib.load(f)
        except Exception as e:
            # Fallback to default in case of corrupted file.
            # Logging is not initialized yet.
            print(
                f"Warning: Failed to load user config from {target_config}: {e}. "
                "Using defaults.",
                file=sys.stderr,
            )

    # 4. Merge parameters
    merged = merge_dicts(default_dict, override_dict)

    # 5. Populate objects
    settings = Settings(
        audio=AudioSettings.from_dict(merged.get("audio", {})),
        stt=STTSettings.from_dict(merged.get("stt", {})),
        llm=LLMSettings.from_dict(merged.get("llm", {})),
        storage=StorageSettings.from_dict(merged.get("storage", {}), default_data_dir),
        logging=LoggingSettings.from_dict(merged.get("logging", {})),
        config_path=target_config if target_config.exists() else None,
    )

    # 6. Validate configuration
    settings.validate()
    return settings


def initialize_user_config(force: bool = False) -> Path:
    """Create directory structure and initialize user configuration template.

    Args:
        force (bool): Overwrite the destination if it already exists.

    Returns:
        Path: Target destination configuration file path.
    """
    config_dir, _ = get_default_paths()
    target_config = config_dir / "config.toml"

    if target_config.exists() and not force:
        return target_config

    # Create directories if missing
    config_dir.mkdir(parents=True, exist_ok=True)

    # Write template copy directly
    default_text = load_default_config_text()
    target_config.write_text(default_text, encoding="utf-8")

    return target_config


def save_settings(settings: Settings) -> None:
    """Serialize the settings object back to the configuration file (TOML format).

    Args:
        settings (Settings): Active application settings.
    """
    config_dir, _ = get_default_paths()
    path = settings.config_path if settings.config_path else config_dir / "config.toml"

    # Ensure parent directories exist
    path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure paths are saved nicely as strings or posix formats
    s_storage = settings.storage
    data_dir_str = s_storage.data_dir.as_posix() if s_storage.data_dir else ""
    log_dir_str = s_storage.log_dir.as_posix() if s_storage.log_dir else ""

    # Generate custom TOML content
    lines = [
        "[audio]",
        f'device = "{settings.audio.device}"',
        f"sample_rate = {settings.audio.sample_rate}",
        f"chunk_duration_ms = {settings.audio.chunk_duration_ms}",
        f"silence_threshold = {settings.audio.silence_threshold}",
        f"silence_duration_s = {settings.audio.silence_duration_s}",
        "",
        "[stt]",
        f'engine = "{settings.stt.engine}"',
        f'vosk_model = "{settings.stt.vosk_model}"',
        f'whisper_model = "{settings.stt.whisper_model}"',
        f'language = "{settings.stt.language}"',
        "",
        "[llm]",
        f'backend = "{settings.llm.backend}"',
        f'ollama_host = "{settings.llm.ollama_host}"',
        f'ollama_model = "{settings.llm.ollama_model}"',
        f"extraction_interval_s = {settings.llm.extraction_interval_s}",
        "",
        "[storage]",
        f'data_dir = "{data_dir_str}"',
        f'log_dir = "{log_dir_str}"',
        "",
        "[logging]",
        f'level = "{settings.logging.level}"',
        f"debug_llm = {str(settings.logging.debug_llm).lower()}",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    settings.config_path = path
