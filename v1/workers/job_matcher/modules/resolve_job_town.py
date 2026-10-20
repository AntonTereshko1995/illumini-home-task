"""Resolve each job's location string to a known UK town and region."""

from __future__ import annotations

import time

from v1.shared.observability.sli_observe import passed, reject, sli_observe
from v1.shared.patterns.logging import get_logger, log_event
from v1.shared.patterns.worker_runtime import ExecutionResult, debug_limits
from v1.workers.job_matcher._shared.town_lookup import lookup_town

MODULE_NAME = "job_matcher__resolve_job_town"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"UNKNOWN_LOCATION"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Tag each row with town / region / country; rows we cannot place are rejected UNKNOWN_LOCATION."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)
    debug_mode, debug_loops = debug_limits()

    # ==================================================================
    # L1: Look up every location
    # ==================================================================
    for i, row in enumerate(prev_data):
        if debug_mode and i >= debug_loops:
            log_event(logger, "debug", "debug_mode_stop", trace_id, stopped_at=i)
            break
        place = lookup_town(row["location"])
        if place is None:
            reject(row, "UNKNOWN_LOCATION")
            continue
        row.update(town=place["town"], region=place["region"], country=place["country"], used_llm=False)

    # ==================================================================
    # L2: Record outcomes, hand on the placed rows
    # ==================================================================
    kept = passed(prev_data)
    log_event(logger, "info", "resolve_job_town_done", trace_id)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id, script_span_id=f"{MODULE_NAME}_{trace_id}", data=kept, artifacts={}, metrics={}
    )
