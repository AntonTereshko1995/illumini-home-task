"""Write one profile's matches to runs/<trace_id>/<profile>_matched.jsonl (shape: OUTPUT_FORMAT.json)."""

from __future__ import annotations

import json
import time

from v1.shared.observability.sli_observe import sli_observe
from v1.shared.patterns.logging import get_logger, log_event
from v1.shared.patterns.worker_runtime import ExecutionResult, debug_limits, run_dir

MODULE_NAME = "job_matcher__portal_matches_output"
MODULE_TYPE = "transform"
REJECTION_REASONS: set[str] = set()
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def record(row: dict, profile_id: str) -> dict:
    """One output line. The required fields come first; the rest help a reviewer read it."""
    return {
        "job_id": row["job_id"],
        "profile_id": profile_id,
        "matched_company": row["matched_company"],
        "matched_job_title": row["matched_job_title"],
        "matched_location": row["matched_location"],
        "reason": row["reason"],
        "used_llm": bool(row.get("used_llm")),
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
    }


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """One JSON line per matched job, in runs/<trace_id>/<file prefix>_matched.jsonl."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)
    debug_mode, debug_loops = debug_limits()

    # ==================================================================
    # L1: Write the file
    # ==================================================================
    out = run_dir(trace_id) / f"{context['output_prefix']}_matched.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for i, row in enumerate(prev_data):
            if debug_mode and i >= debug_loops:
                log_event(logger, "debug", "debug_mode_stop", trace_id, stopped_at=i)
                break
            f.write(json.dumps(record(row, context["profile"]["profile_id"]), ensure_ascii=False) + "\n")

    # ==================================================================
    # L2: Record outcomes
    # ==================================================================
    log_event(logger, "info", "portal_matches_output_done", trace_id, path=str(out))
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=prev_data,
        artifacts={"output_path": str(out)},
        metrics={},
    )
