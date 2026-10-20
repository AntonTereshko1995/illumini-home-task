"""Resolve and normalize the company name from page signals.

Stub: passes scraped company name through unchanged.
TODO: page.structured_job.company > page.h1 > scraped; strip legal suffixes (Ltd, plc, Group, etc.).
"""

from __future__ import annotations

import time

from v2.shared.observability.sli_observe import sli_observe
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__resolve_company"
MODULE_TYPE = "transform"
REJECTION_REASONS: set[str] = set()
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Set row["resolved_company"] from the best available company signal."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()

    for row in prev_data:
        # TODO: page.structured_job.company > page.h1 > scraped; strip legal suffixes
        row["resolved_company"] = row.get("company", "")

    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=prev_data,
        artifacts={},
        metrics={},
    )
