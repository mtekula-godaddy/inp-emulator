"""
Logging utilities for Inputer Performance Monitor.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from rich.logging import RichHandler


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    json_format: bool = False
) -> None:
    """
    Setup structured logging for the application.

    Args:
        level: Logging level
        log_file: Optional log file path
        json_format: Whether to use JSON formatting
    """
    # Configure standard library logging
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="ISO"),
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(pad_event=25))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)

        if json_format:
            file_formatter = logging.Formatter('%(message)s')
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        file_handler.setFormatter(file_formatter)
        logging.getLogger().addHandler(file_handler)