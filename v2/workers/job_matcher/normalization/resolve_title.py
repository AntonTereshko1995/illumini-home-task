"""Resolve the best available job title from page signals.

Stub: passes scraped title through unchanged.
TODO: page.structured_job.title > page.title_tag > page.h1 > scraped.title priority chain.
"""

from __future__ import annotations

import time

from v2.shared.observability.sli_observe import sli_observe
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__resolve_title"
MODULE_TYPE = "transform"
REJECTION_REASONS: set[str] = set()
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Set row["resolved_title"] from the best available title signal."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()

    for row in prev_data:
        # TODO: page.structured_job.title > page.title_tag > page.h1 > scraped.title
        row["resolved_title"] = row.get("title", "")

    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=prev_data,
        artifacts={},
        metrics={},
    )
