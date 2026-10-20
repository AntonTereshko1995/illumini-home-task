"""Keep the jobs that fit one recruiter profile: a listed company, a profile title, a profile location."""

from __future__ import annotations

import time

from v1.shared.observability.sli_observe import passed, reject, sli_observe
from v1.shared.patterns.logging import get_logger, log_event
from v1.shared.patterns.worker_runtime import ExecutionResult, debug_limits
from v1.workers.job_matcher._shared.town_lookup import towns_covered

MODULE_NAME = "job_matcher__match_jobs"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"COMPANY_NOT_LISTED", "NO_TITLE_MATCH", "NO_LOCATION_MATCH"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def matched_titles(job_title: str, titles: list[str]) -> list[str]:
    """Profile titles that appear in the job title."""
    return [t for t in titles if t in job_title]


def matched_locations(town: str, locations: list[dict]) -> list[str]:
    """Profile locations whose town list holds the job's town."""
    return [loc["name"] for loc in locations if town in towns_covered(loc)]


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Filter the located jobs down to context["profile"]; each match carries what it matched."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)
    debug_mode, debug_loops = debug_limits()
    profile = context["profile"]
    companies = {c["name"] for c in profile["companies"]}

    # ==================================================================
    # L1: Test every job against the profile (on a copy: the same jobs feed every profile)
    # ==================================================================
    rows = [dict(r) for r in prev_data]
    for i, row in enumerate(rows):
        if debug_mode and i >= debug_loops:
            log_event(logger, "debug", "debug_mode_stop", trace_id, stopped_at=i)
            break
        if row["company"] not in companies:
            reject(row, "COMPANY_NOT_LISTED")
            continue
        titles = matched_titles(row["title"], profile["titles"])
        if not titles:
            reject(row, "NO_TITLE_MATCH")
            continue
        locations = matched_locations(row["town"], profile["locations"])
        if not locations:
            reject(row, "NO_LOCATION_MATCH")
            continue
        row["matched_company"] = row["company"]
        row["matched_job_title"] = titles
        row["matched_location"] = locations
        row["reason"] = f"{row['title']} at {row['company']}, in {row['town']}"

    # ==================================================================
    # L2: Record outcomes, hand on the matches
    # ==================================================================
    kept = passed(rows)
    log_event(logger, "info", "match_jobs_done", trace_id, profile_id=profile["profile_id"])
    sli_observe(rows, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id, script_span_id=f"{MODULE_NAME}_{trace_id}", data=kept, artifacts={}, metrics={}
    )
