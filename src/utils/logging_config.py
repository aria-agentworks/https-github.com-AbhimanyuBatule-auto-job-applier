"""
Logging setup for the entire application.
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime

from src.core.config import config, LOGS_DIR


def setup_logging():
    """Configure logging for the application."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_level = config.get("app", "log_level", default="INFO")
    log_format = config.get(
        "logging", "format",
        default="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
    )
    max_size = config.get("logging", "max_file_size_mb", default=10) * 1024 * 1024
    backup_count = config.get("logging", "backup_count", default=5)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console)

    # File handler - all logs
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = RotatingFileHandler(
        LOGS_DIR / f"auto_apply_{today}.log",
        maxBytes=max_size,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)

    # Error-only file handler
    error_handler = RotatingFileHandler(
        LOGS_DIR / "errors.log",
        maxBytes=max_size,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(error_handler)

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

    return root_logger
