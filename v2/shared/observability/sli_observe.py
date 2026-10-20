"""Row-level observability: every module tags each row, then records one fact per row.

Tag: META_OUTCOME ("pass" / "rejected" / "error") plus META_REJECTION_REASON or META_ERROR_REASON from the
module's own reason sets. Record: sli_observe(rows, MODULE_NAME, start_time, trace_id) ONCE at the end of
main(), on the FULL row list (passed and rejected). Counting is a group-by over runs/<trace_id>/sli_events.jsonl.
"""

from __future__ import annotations

import json
import time

from v2.shared.patterns.worker_runtime import run_dir

META_OUTCOME = "META_OUTCOME"
META_REJECTION_REASON = "META_REJECTION_REASON"
META_ERROR_REASON = "META_ERROR_REASON"


def passed(rows: list[dict]) -> list[dict]:
    """The rows still tagged "pass"."""
    return [r for r in rows if r.get(META_OUTCOME) == "pass"]


def reject(row: dict, reason: str) -> None:
    """Tag one row as rejected with a reason from the module's REJECTION_REASONS."""
    row[META_OUTCOME] = "rejected"
    row[META_REJECTION_REASON] = reason


def sli_observe(rows: list[dict], module_name: str, start_time: float, trace_id: str) -> None:
    """One fact per row (never totals) in runs/<trace_id>/sli_events.jsonl."""
    duration_ms = round((time.time() - start_time) * 1000)
    with (run_dir(trace_id) / "sli_events.jsonl").open("a", encoding="utf-8") as f:
        for row in rows:
            event = {
                "META_TRACE_ID": trace_id,
                "META_WORKER": module_name.split("__")[0],
                "META_MODULE": module_name,
                "job_id": row.get("job_id") or row.get("_line"),
                META_OUTCOME: row.get(META_OUTCOME, "untagged"),
                META_REJECTION_REASON: row.get(META_REJECTION_REASON),
                META_ERROR_REASON: row.get(META_ERROR_REASON),
                "META_DURATION_MS": duration_ms,
            }
            f.write(json.dumps(event) + "\n")
