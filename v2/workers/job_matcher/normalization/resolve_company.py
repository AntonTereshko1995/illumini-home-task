"""Resolve company name from page signals; soft-filter obviously non-matching companies."""

from __future__ import annotations

import re
import time

from v2.shared.observability.sli_observe import error_out, passed, reject, sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__resolve_company"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"COMPANY_NOT_IN_PROFILE"}
ERROR_REASONS = {"PROCESSING_ERROR"}
WARNING_REASONS: set[str] = set()

_LEGAL_RE = re.compile(
    r"\b(ltd|limited|plc|group|holdings|international|uk|engineering|services|"
    r"solutions|systems|technologies|technology|co|inc|corp|corporation|gmbh|llc|"
    r"company|industries|manufacturing|the|global|europe|consulting|consultancy|"
    r"partners|recruitment|staffing|personnel|associates|agency|firm)\b",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")


def _tokenize(name: str) -> frozenset[str]:
    s = name.lower()
    s = _LEGAL_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    s = _SPACE_RE.sub(" ", s).strip()
    return frozenset(w for w in s.split() if len(w) > 1)


def _resolve_company_name(row: dict) -> str:
    page = row.get("page") or {}
    sj = page.get("structured_job") or {}
    structured = (sj.get("company") or "").strip()
    if structured:
        return structured
    return row.get("company", "").strip()


def _build_profile_tokens(companies: list) -> frozenset[str]:
    tokens: set[str] = set()
    for c in companies:
        name = c.get("name", "") if isinstance(c, dict) else str(c)
        tokens.update(_tokenize(name))
    return frozenset(tokens)


logger = get_logger(MODULE_NAME)


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    log_event(logger, "info", "module_start", trace_id, input_count=len(prev_data))

    profile_tokens = _build_profile_tokens(context["profile"].get("companies") or [])

    for row in prev_data:
        try:
            resolved = _resolve_company_name(row)
            row["resolved_company"] = resolved
            if not _tokenize(resolved) & profile_tokens:
                reject(row, "COMPANY_NOT_IN_PROFILE")
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
