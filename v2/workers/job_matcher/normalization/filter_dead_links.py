"""Remove jobs with dead HTTP links (404 or 410) before any resolution work."""

from __future__ import annotations

import time

from v2.shared.observability.sli_observe import passed, reject, sli_observe
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__filter_dead_links"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"DEAD_LINK"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Reject rows whose page.http_status is 404 or 410."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()

    for row in prev_data:
        if row.get("page", {}).get("http_status") in (404, 410):
            reject(row, "DEAD_LINK")

    kept = passed(prev_data)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=kept,
        artifacts={},
        metrics={},
    )
