"""LLM agent: decide which jobs match the recruiter profile (company × title × location)."""

from __future__ import annotations

import asyncio
import re
import time

from v2.shared.api_calls.llm import BudgetExceeded, NoulQuestion, decide_async
from v2.shared.observability.sli_observe import passed, reject, sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__match_jobs"
REJECTION_REASONS = {
    "WRONG_COMPANY",
    "WRONG_TITLE",
    "WRONG_LOCATION",
    "WRONG_COUNTRY",
    "MULTI_FAIL",
}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()

_CONCURRENCY = 10  # max parallel jev calls; stays within rate limits
_MATCH_THRESHOLD = 0.5

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(ltd|plc|group|holdings|international|uk|limited|the|co|corp|inc)\b",
    re.IGNORECASE,
)

# Unambiguous non-UK location markers (lowercase); extend as needed for other countries.
_OUTSIDE_UK_MARKERS = (
    "united states",
    "united states of america",
    "canada",
    "australia",
    "new zealand",
    " pa,",
    " tx,",
    " ny,",
    " ca,",
    " fl,",
    " va,",
    " al ",
    " al,",
)

_TITLE_SPLIT_RE = re.compile(r"[^a-z0-9\s]")


def _normalize_tokens(name: str) -> frozenset[str]:
    name = _LEGAL_SUFFIX_RE.sub(" ", name)
    name = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    return frozenset(name.split())


def _find_matched_company(resolved: str, candidates: list[str]) -> str | None:
    """Return the canonical company name whose normalised tokens all appear in resolved."""
    if not resolved:
        return None
    resolved_tokens = _normalize_tokens(resolved)
    if not resolved_tokens:
        return None
    best: str | None = None
    best_score = 0
    for name in candidates:
        tokens = _normalize_tokens(name)
        if not tokens:
            continue
        overlap = len(tokens & resolved_tokens)
        if overlap == len(tokens) and overlap > best_score:
            best = name
            best_score = overlap
    return best


def _detect_location_country(location_strings: list[str]) -> str:
    """Return 'United States', 'United Kingdom', or '' (unknown).

    Only fires on unambiguous signals (country names or US state codes).
    Latin-script foreign cities without country suffix → return '' so the
    agent stage can decide.
    """
    lower_strings = [s.lower() for s in location_strings]
    for s in lower_strings:
        if any(m in s for m in _OUTSIDE_UK_MARKERS):
            return "United States"
    for s in lower_strings:
        if "united kingdom" in s or " uk" in s or ", gb" in s:
            return "United Kingdom"
    return ""


def _derive_rejection_reason(
    answers: dict,
    asked_title_indices: list[int],
    n_locs: int,
    location_strings: list[str],
) -> str:
    """Deterministic rejection reason; called only when the row is being rejected."""
    company_ans = answers.get("company")
    if not company_ans or company_ans.noul <= _MATCH_THRESHOLD:
        return "WRONG_COMPANY"

    has_title = any((a := answers.get(f"title_{i}")) and a.noul > _MATCH_THRESHOLD for i in asked_title_indices)
    if not has_title:
        return "WRONG_TITLE"

    # Company + title passed; location failed
    country = _detect_location_country(location_strings)
    if country and country != "United Kingdom":
        return "WRONG_COUNTRY"
    return "WRONG_LOCATION"


def _title_word_set(text: str) -> frozenset[str]:
    words = _TITLE_SPLIT_RE.sub(" ", text.lower()).split()
    return frozenset(w.rstrip("s") for w in words if len(w) > 2)


def _relevant_title_indices(job_title: str, titles: list[str]) -> list[int]:
    """Indices of profile titles that share ≥1 word with the job title."""
    job_words = _title_word_set(job_title)
    return [i for i, t in enumerate(titles) if _title_word_set(t) & job_words]


def _job_state(row: dict) -> dict:
    page = row.get("page") or {}
    sj = page.get("structured_job") or {}
    # Deduplicate preserving order; avoids sending the same location string twice.
    raw_strings = row.get("location_strings") or []
    location_strings = list(dict.fromkeys(raw_strings))
    return {
        "company": row.get("resolved_company") or row.get("company") or sj.get("company") or "",
        "title": row.get("resolved_title") or row.get("title") or sj.get("title") or "",
        "location_strings": location_strings,
        "location_country": _detect_location_country(location_strings),
        "is_remote": bool(row.get("is_remote_hint")),
        "title_tag": (page.get("title_tag") or "")[:120],
        # url intentionally excluded: sanitized feed.example URLs carry no company
        # name signal and the instruction "Consider the company in url" would mislead
        # the model. Re-add only if source_url reliably encodes the company name.
    }


def _build_questions(companies: list[str], titles: list[str], locations: list[dict]) -> dict:
    """Build the base per-profile question dict (title_* and loc_* only).

    Company question is built per-row in _process_row (single candidate, not full list).
    rejection_reason ChoiceQuestion removed; reason is now derived deterministically.
    """
    questions: dict = {}

    # Titles: one NoulQuestion per target title; no criteria= (NoulQuestion only needs instructions)
    for i, title in enumerate(titles):
        questions[f"title_{i}"] = NoulQuestion(
            instructions=(
                f"Does the job title contain every word from '{title}'? "
                "Word order doesn't matter; ignore case and punctuation; treat trailing 's' as plural."
            ),
        )

    # Locations: one NoulQuestion per target location; no criteria=
    for i, loc in enumerate(locations):
        name = loc["name"]
        loc_type = loc.get("type", "")
        includes = loc.get("includes") or []
        country = loc.get("country", "United Kingdom")
        if loc_type == "remote":
            instruction = f"Is this job declared as remote or home-based work in {country} ('{name}')?"
        else:
            inc_str = f" Includes: {', '.join(includes)}." if includes else ""
            instruction = f"Is this job located in '{name}' ({loc_type}) in {country}?{inc_str}"
        questions[f"loc_{i}"] = NoulQuestion(instructions=instruction)

    return questions


async def _process_row(
    sem: asyncio.Semaphore,
    row: dict,
    questions: dict,
    companies: list,
    titles: list,
    locations: list,
    logger,
    trace_id: str,
) -> None:
    state = _job_state(row)

    # Early exit: if no profile company matches, skip the jev call entirely.
    candidate_company = _find_matched_company(state["company"], companies)
    if candidate_company is None:
        reject(row, "WRONG_COMPANY")
        return

    # Pre-filter title questions: only send titles sharing ≥1 word with job title.
    asked_title_indices = _relevant_title_indices(state["title"], titles)

    # Build per-row question set: filtered titles + all loc_* + single-candidate company.
    row_questions: dict = {}
    for i in asked_title_indices:
        row_questions[f"title_{i}"] = questions[f"title_{i}"]
    for k, v in questions.items():
        if k.startswith("loc_"):
            row_questions[k] = v
    row_questions["company"] = NoulQuestion(
        instructions=(
            f"Does this job page belong to '{candidate_company}'? "
            "Ignore case, a leading 'The', and legal suffixes "
            "(Ltd, plc, Group, Holdings, Corp, UK, Engineering, Systems). "
            "Consider title_tag and title."
        ),
    )

    async with sem:
        try:
            answers = await decide_async(state, row_questions, purpose="job_matching")
        except BudgetExceeded:
            raise
        except Exception as exc:
            log_event(logger, "error", "llm_job_failed", trace_id, error=str(exc), job_id=row.get("job_id"))
            row["META_ERROR_REASON"] = "LLM_ERROR"
            return

    company_ans = answers.get("company")
    if not company_ans or company_ans.noul <= _MATCH_THRESHOLD:
        reject(row, _derive_rejection_reason(answers, asked_title_indices, len(locations), state["location_strings"]))
        return

    matched_titles = [
        titles[i] for i in asked_title_indices if (a := answers.get(f"title_{i}")) and a.noul > _MATCH_THRESHOLD
    ]
    if not matched_titles:
        reject(row, _derive_rejection_reason(answers, asked_title_indices, len(locations), state["location_strings"]))
        return

    matched_locs = [
        locations[i]["name"]
        for i in range(len(locations))
        if (a := answers.get(f"loc_{i}")) and a.noul > _MATCH_THRESHOLD
    ]
    if not matched_locs:
        reject(row, _derive_rejection_reason(answers, asked_title_indices, len(locations), state["location_strings"]))
        return

    row["matched_company"] = candidate_company
    row["matched_job_title"] = matched_titles
    row["matched_location"] = matched_locs
    row["reason"] = f"jev: company={candidate_company}, titles={matched_titles}, locations={matched_locs}"
    row["used_llm"] = True


async def _process_all(
    rows: list[dict],
    questions: dict,
    companies: list,
    titles: list,
    locations: list,
    logger,
    trace_id: str,
    sem: asyncio.Semaphore | None = None,
) -> None:
    if sem is None:
        sem = asyncio.Semaphore(_CONCURRENCY)
    await asyncio.gather(
        *[_process_row(sem, row, questions, companies, titles, locations, logger, trace_id) for row in rows]
    )


async def main_async(
    context: dict,
    prev_data: list[dict],
    sem: asyncio.Semaphore | None = None,
) -> ExecutionResult:
    """Async entry point — accepts a shared semaphore from chunk_runner for global concurrency control."""
    trace_id: str = context.get("trace_id") or ""
    start_time = time.time()
    logger = get_logger(MODULE_NAME)

    profile = context["profile"]
    companies = [c["name"] if isinstance(c, dict) else c for c in profile.get("companies") or []]
    titles = profile.get("titles") or []
    locations = profile.get("locations") or []

    questions = _build_questions(companies, titles, locations)
    log_event(logger, "info", "module_start", trace_id, input_count=len(prev_data))

    await _process_all(prev_data, questions, companies, titles, locations, logger, trace_id, sem=sem)

    kept = passed(prev_data)
    log_event(logger, "info", "module_done", trace_id, matched=len(kept), total=len(prev_data))
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=kept,
        artifacts={},
        metrics={},
    )


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    return asyncio.run(main_async(context, prev_data))
