"""Deduplicate jobs by job_id (v2 fix: not by title|company as in v1)."""

from __future__ import annotations

import time

from v2.shared.observability.sli_observe import error_out, passed, reject, sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__filter_duplicates"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"DUPLICATE"}
ERROR_REASONS = {"PROCESSING_ERROR"}
WARNING_REASONS: set[str] = set()


logger = get_logger(MODULE_NAME)


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Keep the first occurrence of each job_id; reject subsequent duplicates."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    log_event(logger, "info", "module_start", trace_id, input_count=len(prev_data))

    seen: set[str] = set()
    for row in prev_data:
        try:
            key = row["job_id"]
            if key in seen:
                reject(row, "DUPLICATE")
            else:
                seen.add(key)
        except Exception as exc:
            log_event(logger, "error", "row_error", trace_id, job_id=row.get("job_id"), error=str(exc))
            error_out(row, "PROCESSING_ERROR")

    kept = passed(prev_data)
    log_event(logger, "info", "module_done", trace_id, kept=len(kept), dropped=len(prev_data) - len(kept))
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=kept,
        artifacts={},
        metrics={},
    )
