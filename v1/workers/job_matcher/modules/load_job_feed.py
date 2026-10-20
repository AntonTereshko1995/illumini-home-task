"""Read the raw job feed (one JSON object per line) into rows."""

from __future__ import annotations

import json
import time
from pathlib import Path

from v1.shared.observability.sli_observe import META_OUTCOME, passed, reject, sli_observe
from v1.shared.patterns.logging import get_logger, log_event
from v1.shared.patterns.worker_runtime import ExecutionResult, debug_limits

MODULE_NAME = "job_matcher__load_job_feed"
MODULE_TYPE = "transform"
REJECTION_REASONS = {"INVALID_JSON", "NOT_AN_OBJECT"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Load context["jobs_path"]; lines that are not a JSON object are rejected and counted."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)
    debug_mode, debug_loops = debug_limits()

    # ==================================================================
    # L1: Parse every line
    # ==================================================================
    rows: list[dict] = []
    with Path(context["jobs_path"]).open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if debug_mode and line_no - 1 >= debug_loops:
                log_event(logger, "debug", "debug_mode_stop", trace_id, stopped_at=line_no - 1)
                break
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                raw = {"_line": line_no}
                reject(raw, "INVALID_JSON")
                rows.append(raw)
                continue
            if not isinstance(raw, dict):
                rows.append({"_line": line_no})
                reject(rows[-1], "NOT_AN_OBJECT")
                continue
            rows.append({**raw, META_OUTCOME: "pass"})

    # ==================================================================
    # L2: Record outcomes, hand on the parsed rows
    # ==================================================================
    log_event(logger, "info", "load_job_feed_done", trace_id, jobs_path=context["jobs_path"])
    sli_observe(rows, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id, script_span_id=f"{MODULE_NAME}_{trace_id}", data=passed(rows), artifacts={}, metrics={}
    )
