"""Read the raw job feed (one JSON object per line) and flatten scraped.* into canonical shape."""

from __future__ import annotations

import json
import time
from pathlib import Path

from v2.shared.observability.sli_observe import META_OUTCOME, META_REJECTION_REASON, passed, sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult, debug_limits

MODULE_NAME = "job_matcher__load_job_feed"
MODULE_TYPE = "transform"
REJECTION_REASONS = {"INVALID_JSON", "NOT_AN_OBJECT", "MALFORMED_ROW"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()


def _parse_salary(value: object) -> int | None:
    # TODO: handle "£50K", "45,000", range strings
    if value is None or value == "":
        return None
    try:
        return int(str(value).replace("£", "").replace(",", "").strip())
    except ValueError:
        return None


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Load context["jobs_path"]; flatten scraped.* into canonical fields; reject malformed rows."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    logger = get_logger(MODULE_NAME)
    debug_mode, debug_loops = debug_limits()

    rows: list[dict] = []
    with Path(context["jobs_path"]).open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if debug_mode and line_no - 1 >= debug_loops:
                log_event(logger, "debug", "debug_mode_stop", trace_id, stopped_at=line_no - 1)
                break
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                rows.append(
                    {
                        "_line": line_no,
                        META_OUTCOME: "rejected",
                        META_REJECTION_REASON: "INVALID_JSON",
                    }
                )
                continue
            if not isinstance(raw, dict):
                rows.append(
                    {
                        "_line": line_no,
                        META_OUTCOME: "rejected",
                        META_REJECTION_REASON: "NOT_AN_OBJECT",
                    }
                )
                continue
            scraped = raw.get("scraped")
            if not isinstance(scraped, dict):
                row = {**raw, META_OUTCOME: "rejected", META_REJECTION_REASON: "MALFORMED_ROW"}
                rows.append(row)
                continue
            rows.append(
                {
                    "job_id": raw["job_id"],
                    "title": scraped.get("title", "").strip(),
                    "company": scraped.get("company", "").strip(),
                    "location": scraped.get("location", "").strip(),
                    "salary_gbp": _parse_salary(scraped.get("salary")),
                    "source_url": raw.get("source_url") or "",
                    "page": raw.get("page") or {},
                    META_OUTCOME: "pass",
                }
            )

    log_event(logger, "info", "load_job_feed_done", trace_id, jobs_path=context["jobs_path"])
    sli_observe(rows, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=passed(rows),
        artifacts={},
        metrics={},
    )
