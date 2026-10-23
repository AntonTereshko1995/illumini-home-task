"""Resolve job title from page signals; soft-filter obviously non-matching titles."""

from __future__ import annotations

import re
import time

from v2.shared.observability.sli_observe import error_out, passed, reject, sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__resolve_title"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"TITLE_NOT_IN_PROFILE"}
ERROR_REASONS = {"PROCESSING_ERROR"}
WARNING_REASONS: set[str] = set()

_TAG_SPLIT_RE = re.compile(r"[|\-–—]")
_WORD_SPLIT_RE = re.compile(r"[\s\-/|.,&()+]+")


def _title_words(title: str) -> frozenset[str]:
    tokens = set()
    for w in _WORD_SPLIT_RE.split(title.lower()):
        if not w:
            continue
        if len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        tokens.add(w)
    return frozenset(tokens)


def _resolve_title(row: dict) -> str:
    page = row.get("page") or {}
    sj = page.get("structured_job") or {}

    structured = (sj.get("title") or "").strip()
    if structured:
        return structured

    tag = (page.get("title_tag") or "").strip()
    if tag:
        return _TAG_SPLIT_RE.split(tag)[0].strip()

    h1 = (page.get("h1") or "").strip()
    if h1:
        return h1

    return row.get("title", "").strip()


def _build_profile_title_words(titles: list) -> frozenset[str]:
    tokens: set[str] = set()
    for t in titles:
        name = t if isinstance(t, str) else t.get("title", "")
        tokens.update(_title_words(name))
    return frozenset(tokens)


logger = get_logger(MODULE_NAME)


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    trace_id: str = context.get("trace_id")
    start_time = time.time()
    log_event(logger, "info", "module_start", trace_id, input_count=len(prev_data))

    profile_title_words = _build_profile_title_words(context["profile"].get("titles") or [])

    for row in prev_data:
        try:
            resolved = _resolve_title(row)
            row["resolved_title"] = resolved
            if not _title_words(resolved) & profile_title_words:
                reject(row, "TITLE_NOT_IN_PROFILE")
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
