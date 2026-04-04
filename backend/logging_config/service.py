"""Logger factory — configures and provides structured loggers."""

import logging
import sys
from pathlib import Path

from backend.logging_config.filters import CredentialMaskingFilter
from backend.logging_config.formatters import JsonFormatter, HumanFormatter

_initialized = False


def setup_logging(
    level: str = "INFO",
    fmt: str = "json",
    file_path: str | None = None,
    mask_credentials: bool = True,
) -> None:
    """Configure the root logger with formatters and handlers.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Output format ('json' or 'human').
        file_path: Optional log file path.
        mask_credentials: Whether to mask credential values in logs.
    """
    global _initialized

    root = logging.getLogger("polyfast")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers on re-init
    root.handlers.clear()

    # Choose formatter
    formatter = JsonFormatter() if fmt == "json" else HumanFormatter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler
    if file_path:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())  # Always JSON for file
        root.addHandler(file_handler)

    # Credential masking filter
    if mask_credentials:
        masking_filter = CredentialMaskingFilter()
        for handler in root.handlers:
            handler.addFilter(masking_filter)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the polyfast namespace."""
    return logging.getLogger(f"polyfast.{name}")


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    entity_type: str = "",
    entity_id: str = "",
    payload: dict | None = None,
) -> None:
    """Emit a structured log event with entity context.

    Args:
        logger: The logger instance.
        level: Log level (e.g., logging.INFO).
        message: Human-readable message.
        entity_type: Type of entity (e.g., 'discovery', 'order').
        entity_id: Identifier of the entity.
        payload: Additional structured data.
    """
    logger.log(
        level,
        message,
        extra={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
        },
    )
