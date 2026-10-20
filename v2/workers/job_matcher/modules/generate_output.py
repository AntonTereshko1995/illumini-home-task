"""Write matched rows to the output JSONL file (one JSON line per matched job)."""

from __future__ import annotations

import json
import time

from v2.shared.observability.sli_observe import sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult, run_dir

MODULE_NAME = "job_matcher__generate_output"
MODULE_TYPE = "transform"
REJECTION_REASONS: set[str] = set()
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def _record(row: dict, profile_id: str) -> dict:
    return {
        "job_id": row["job_id"],
        "profile_id": profile_id,
        "matched_company": row["matched_company"],
        "matched_job_title": row["matched_job_title"],
        "matched_location": row["matched_location"],
        "reason": row["reason"],
        "used_llm": bool(row.get("used_llm")),
    }


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Write rows the agent stage matched (have matched_company set) to the output file."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)

    out = run_dir(trace_id) / f"{context['output_prefix']}_matched.jsonl"
    matched = [r for r in prev_data if r.get("matched_company")]
    with out.open("w", encoding="utf-8") as f:
        for row in matched:
            f.write(json.dumps(_record(row, context["profile"]["profile_id"]), ensure_ascii=False) + "\n")

    log_event(logger, "info", "generate_output_done", trace_id, output_path=str(out), matched=len(matched))
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=matched,
        artifacts={"output_path": str(out)},
        metrics={},
    )
