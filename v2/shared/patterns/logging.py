"""Structured logging: every line is `<time> | <LEVEL> | <logger> | <JSON payload>` with an `event` field."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

_file_handler: logging.FileHandler | None = None
_handler_lock = threading.Lock()


def configure_file_logging(run_dir: Path) -> None:
    """Add a FileHandler writing to run_dir/logs.jsonl. Call once per run after run_dir is created."""
    global _file_handler
    new_handler = logging.FileHandler(run_dir / "logs.jsonl", encoding="utf-8")
    new_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    with _handler_lock:
        # Add first so there is never a window with no file handler attached.
        logging.getLogger().addHandler(new_handler)
        if _file_handler is not None:
            logging.getLogger().removeHandler(_file_handler)
            _file_handler.close()
        _file_handler = new_handler


def get_logger(name: str) -> logging.Logger:
    """A logger named after the module (MODULE_NAME) or handler (HANDLER_NAME); level from LOG_LEVEL."""
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format=LOG_FORMAT)
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: str, event: str, trace_id: str, **kwargs: Any) -> None:
    """One structured log line: {"event": ..., "trace_id": ..., **kwargs}. Facts only, never row totals."""
    getattr(logger, level)(json.dumps({"event": event, "trace_id": trace_id, **kwargs}, default=str))
