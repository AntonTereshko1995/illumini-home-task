"""Drop jobs the feed carries more than once (the same job re-posted)."""

from __future__ import annotations

import time

from v1.shared.observability.sli_observe import passed, reject, sli_observe
from v1.shared.patterns.logging import get_logger, log_event
from v1.shared.patterns.worker_runtime import ExecutionResult, debug_limits

MODULE_NAME = "job_matcher__drop_duplicate_jobs"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"DUPLICATE"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def dedupe_key(row: dict) -> str:
    return f"{row['title']}|{row['company']}"


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Keep the first row per dedupe key; later ones are rejected as DUPLICATE."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)
    debug_mode, debug_loops = debug_limits()

    # ==================================================================
    # L1: First row per key wins
    # ==================================================================
    seen: set[str] = set()
    for i, row in enumerate(prev_data):
        if debug_mode and i >= debug_loops:
            log_event(logger, "debug", "debug_mode_stop", trace_id, stopped_at=i)
            break
        key = dedupe_key(row)
        if key in seen:
            reject(row, "DUPLICATE")
        seen.add(key)

    # ==================================================================
    # L2: Record outcomes, hand on the survivors
    # ==================================================================
    kept = passed(prev_data)
    log_event(logger, "info", "drop_duplicate_jobs_done", trace_id)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id, script_span_id=f"{MODULE_NAME}_{trace_id}", data=kept, artifacts={}, metrics={}
    )
