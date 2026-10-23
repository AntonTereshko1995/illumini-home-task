"""Collect location strings and tag remote hints; drop jobs provably outside the profile country."""

from __future__ import annotations

import re
import time

from v2.shared.observability.sli_observe import error_out, passed, reject, sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__normalise_location"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"LOCATION_NOT_IN_PROFILE"}
ERROR_REASONS = {"PROCESSING_ERROR"}
WARNING_REASONS: set[str] = set()

_PLACEHOLDER_RE = re.compile(r"^\d+\s+location", re.IGNORECASE)
_REMOTE_RE = re.compile(r"\b(remote|home.based|work from home|wfh|home based)\b", re.IGNORECASE)
_NON_LATIN_RE = re.compile(r"[　-鿿가-힯Ѐ-ӿ]")  # CJK / Korean / Cyrillic


def _collect_location_strings(row: dict) -> list[str]:
    """All location text for metadata / downstream use."""
    strings: list[str] = []
    page = row.get("page") or {}
    sj = page.get("structured_job") or {}

    for loc in sj.get("locations") or []:
        if loc and str(loc).strip():
            strings.append(str(loc).strip())

    sj_loc = (sj.get("location") or "").strip()
    if sj_loc:
        strings.append(sj_loc)
    for loc in sj.get("additional_locations") or []:
        if loc and str(loc).strip():
            strings.append(str(loc).strip())

    scraped = (row.get("location") or "").strip()
    if scraped and not _PLACEHOLDER_RE.match(scraped):
        strings.append(scraped)

    return strings


def _has_non_latin(strings: list[str]) -> bool:
    """True if any location string contains non-Latin script (CJK / Korean / Cyrillic).

    These are unambiguously non-UK and safe to reject early.  Latin-script
    foreign cities (e.g. "Birmingham, AL") are excluded because multinational
    companies sometimes declare the wrong city; the agent stage handles those.
    """
    return any(_NON_LATIN_RE.search(s) for s in strings)


logger = get_logger(MODULE_NAME)


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    trace_id = context.get("trace_id")
    start_time = time.time()
    log_event(logger, "info", "module_start", trace_id, input_count=len(prev_data))

    has_remote_profile = any(loc.get("type") == "remote" for loc in context["profile"].get("locations") or [])

    for row in prev_data:
        try:
            strings = _collect_location_strings(row)
            row["location_strings"] = strings

            is_remote = any(_REMOTE_RE.search(s) for s in strings)
            row["is_remote_hint"] = is_remote

            if is_remote and has_remote_profile:
                continue

            if _has_non_latin(strings):
                reject(row, "LOCATION_NOT_IN_PROFILE")
        except Exception as exc:
            log_event(logger, "error", "row_error", trace_id, job_id=row.get("job_id"), error=str(exc))
            error_out(row, "PROCESSING_ERROR")

    kept = passed(prev_data)
    log_event(logger, "info", "module_done", trace_id, kept=len(kept), dropped=len(prev_data) - len(kept))
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=kept,
        artifacts={},
        metrics={},
    )
