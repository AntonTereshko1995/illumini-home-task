"""Turn raw feed rows into one clean shape: job_id, title, company, location, salary_gbp, source_url, page."""

from __future__ import annotations

import time

from v1.shared.observability.sli_observe import META_OUTCOME, sli_observe
from v1.shared.patterns.logging import get_logger, log_event
from v1.shared.patterns.worker_runtime import ExecutionResult, debug_limits

MODULE_NAME = "job_matcher__normalise_job_rows"
MODULE_TYPE = "transform"
REJECTION_REASONS: set[str] = set()
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def parse_salary(value: object) -> int | None:
    """'£45,000' / '45000' -> 45000. Empty -> None."""
    if value is None or value == "":
        return None
    return int(str(value).replace("£", "").replace(",", "").strip())


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Normalise every row to the shape the rest of the pipeline reads (our stored fields, plus the fetched page)."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)
    debug_mode, debug_loops = debug_limits()

    # ==================================================================
    # L1: Map raw fields to the clean shape
    # ==================================================================
    rows: list[dict] = []
    for i, raw in enumerate(prev_data):
        if debug_mode and i >= debug_loops:
            log_event(logger, "debug", "debug_mode_stop", trace_id, stopped_at=i)
            break
        try:
            scraped = raw["scraped"]
            rows.append(
                {
                    "job_id": raw["job_id"],
                    "title": scraped["title"].strip(),
                    "company": scraped["company"].strip(),
                    "location": scraped["location"].strip(),
                    "salary_gbp": parse_salary(scraped.get("salary")),
                    "source_url": raw.get("source_url") or "",
                    "page": raw.get("page") or {},
                    META_OUTCOME: "pass",
                }
            )
        except Exception:
            pass

    # ==================================================================
    # L2: Record outcomes
    # ==================================================================
    log_event(logger, "info", "normalise_job_rows_done", trace_id)
    sli_observe(rows, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id, script_span_id=f"{MODULE_NAME}_{trace_id}", data=rows, artifacts={}, metrics={}
    )
