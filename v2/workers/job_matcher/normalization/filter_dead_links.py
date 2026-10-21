"""Remove jobs with dead HTTP links (404 or 410) before any resolution work."""

from __future__ import annotations

import time

from v2.shared.observability.sli_observe import passed, reject, sli_observe
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__filter_dead_links"
MODULE_TYPE = "filter"
# 404/410: explicitly dead; 403/405: blocked — page unreadable, job unverifiable
REJECTION_REASONS = {"DEAD_LINK", "BLOCKED_PAGE"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()

_DEAD_STATUSES = frozenset({404, 410})
_BLOCKED_STATUSES = frozenset({403, 405})


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Reject rows whose page could not be confirmed: dead (404/410) or blocked (403/405)."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()

    for row in prev_data:
        page = row.get("page") or {}
        status = page.get("http_status")
        if status in _DEAD_STATUSES:
            reject(row, "DEAD_LINK")
            continue
        if status in _BLOCKED_STATUSES:
            reject(row, "BLOCKED_PAGE")
            continue
        # Page rendered but no structured content at all — job is unverifiable
        sj = page.get("structured_job") or {}
        if not sj.get("title") and not (page.get("h1") or "").strip() and not sj.get("company"):
            reject(row, "BLOCKED_PAGE")

    kept = passed(prev_data)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=kept,
        artifacts={},
        metrics={},
    )
