"""Structured logging configurations with rotation and dynamic session contexts."""

from __future__ import annotations

import contextvars
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from taskify.config import Settings

# Thread-safe context variable to store the current capture session ID
session_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "session_id", default="N/A"
)


class SessionIDFilter(logging.Filter):
    """Injects the active session ID into log records for structured output."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add session_id attribute from ContextVar to the log record."""
        record.session_id = session_id_ctx.get()
        return True


def set_active_session_id(session_id: str | None) -> None:
    """Set the active recording session identifier in context.

    Args:
        session_id (str, optional): Target UUID session string or None to reset.
    """
    session_id_ctx.set(session_id if session_id else "N/A")


def configure_logging(settings: Settings) -> None:
    """Initialize structured console and rotating file logging handlers.

    Args:
        settings (Settings): Active configuration blocks containing levels/paths.
    """
    # 1. Clear existing handlers on the root logger to prevent duplicate logs
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # 2. Determine base log levels
    global_level_str = settings.logging.level.upper()
    global_level = getattr(logging, global_level_str, logging.INFO)

    # If debug_llm is enabled, root accepts DEBUG so they propagate to handlers
    if settings.logging.debug_llm and global_level > logging.DEBUG:
        root_logger.setLevel(logging.DEBUG)

        # Restrict other subsystems to the global level
        logging.getLogger("taskify.audio").setLevel(global_level)
        logging.getLogger("taskify.stt").setLevel(global_level)
        logging.getLogger("taskify.storage").setLevel(global_level)
        logging.getLogger("taskify.pipeline").setLevel(global_level)
        logging.getLogger("taskify.ui").setLevel(global_level)
        # Explicity debug LLM
        logging.getLogger("taskify.llm").setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(global_level)

    # 3. Formatter including module, threadName, and session_id context
    fmt_str = (
        "%(asctime)s [%(levelname)s] [%(module)s:%(threadName)s] "
        "[Session: %(session_id)s] %(message)s"
    )
    formatter = logging.Formatter(fmt_str)
    session_filter = SessionIDFilter()

    # 4. Console Handler (Write INFO+ or DEBUG if requested globally)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(global_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(session_filter)
    root_logger.addHandler(console_handler)

    # 5. Rotating File Handler (10 MB per file, max 5 backups)
    log_dir = settings.storage.log_dir
    if not log_dir:
        # Fallback default path
        log_dir = Path.home() / ".local" / "share" / "taskify"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    try:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(global_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(session_filter)
        root_logger.addHandler(file_handler)
    except OSError as e:
        # Gracefully log console warning if file write is locked/forbidden
        logging.warning("Failed to configure rotating file handler: %s", e)
