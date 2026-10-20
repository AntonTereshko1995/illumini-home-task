"""Deduplicate jobs by job_id (v2 fix: not by title|company as in v1)."""

from __future__ import annotations

import time

from v2.shared.observability.sli_observe import passed, reject, sli_observe
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__filter_duplicates"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"DUPLICATE"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Keep the first occurrence of each job_id; reject subsequent duplicates."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()

    seen: set[str] = set()
    for row in prev_data:
        key = row["job_id"]
        if key in seen:
            reject(row, "DUPLICATE")
        else:
            seen.add(key)

    kept = passed(prev_data)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=kept,
        artifacts={},
        metrics={},
    )
