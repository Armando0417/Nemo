from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


LOG_FILE = Path(os.getenv("NEMO_LOG_FILE", "nemo.log")).expanduser()


class NemoConsoleFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[35m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool):
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s",
            datefmt="%H:%M:%S",
        )
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        if not self.use_color:
            return rendered
        color = self.COLORS.get(record.levelno)
        return f"{color}{rendered}{self.RESET}" if color else rendered


def configure_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_nemo_logging_configured", False):
        return

    level_name = os.getenv("NEMO_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(NemoConsoleFormatter(use_color=sys.stdout.isatty()))

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-18s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)
    root._nemo_logging_configured = True

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("nemo.server").info("Nemo logging online. Terminal output and %s are active.", LOG_FILE)
