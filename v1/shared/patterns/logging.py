"""Structured logging: every line is `<time> | <LEVEL> | <logger> | <JSON payload>` with an `event` field."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    """A logger named after the module (MODULE_NAME) or handler (HANDLER_NAME); level from LOG_LEVEL."""
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format=LOG_FORMAT)
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: str, event: str, trace_id: str, **kwargs: Any) -> None:
    """One structured log line: {"event": ..., "trace_id": ..., **kwargs}. Facts only, never row totals."""
    getattr(logger, level)(json.dumps({"event": event, "trace_id": trace_id, **kwargs}, default=str))
