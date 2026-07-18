"""
Central logging configuration.

Usage (once, at app startup — e.g. top of main.py or dashboard entrypoint):
    from eliteprocareers.logging_setup import setup_logging
    setup_logging()

Usage (everywhere else):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Something happened")

Logs are written outside the repo (~/eliteprocareers-logs/) so they never
risk being committed to git, since job data, AI responses, and API payloads
may end up in log output over time.
"""

import logging
import logging.handlers
from pathlib import Path

from eliteprocareers.config import settings

LOG_DIR = Path.home() / "eliteprocareers-logs"
LOG_FILE = LOG_DIR / "eliteprocareers.log"

# Rotate at 5MB, keep 5 old files (~25MB max on disk)
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logging() -> None:
    """Configure root logger with console + rotating file output.

    Safe to call multiple times — won't duplicate handlers.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()

    # Avoid duplicate handlers if called more than once (e.g. in tests)
    if root_logger.handlers:
        return

    root_logger.setLevel(settings.log_level.upper())

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logging.getLogger(__name__).info(
        "Logging initialized (level=%s, file=%s)", settings.log_level.upper(), LOG_FILE
    )
