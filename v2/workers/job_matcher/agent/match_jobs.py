"""LLM agent: decide which jobs match the recruiter profile (company × title × location)."""

from __future__ import annotations

import asyncio
import re
import time

from v2.shared.api_calls.llm import BudgetExceeded, ChoiceQuestion, NoulQuestion, decide_async
from v2.shared.observability.sli_observe import passed, reject, sli_observe
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__match_jobs"
REJECTION_REASONS = {
    "WRONG_COMPANY",
    "WRONG_TITLE",
    "WRONG_LOCATION",
    "WRONG_COUNTRY",
    "DEAD_LINK",
    "MULTI_FAIL",
    "NO_MATCH",  # fallback when jev answer is missing
}
_CONCURRENCY = 10  # max parallel jev calls; stays within rate limits
_REJECTION_CRITERIA = {
    "WRONG_COMPANY": "Company is not in the target list",
    "WRONG_TITLE": "Job title doesn't fit any target title",
    "WRONG_LOCATION": "Location is outside the target areas",
    "WRONG_COUNTRY": "Job is in a different country",
    "DEAD_LINK": "Page is unavailable (404/410)",
    "MULTI_FAIL": "Multiple criteria fail simultaneously",
}

_MATCH_THRESHOLD = 0.5

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(ltd|plc|group|holdings|international|uk|limited|the|co|corp|inc)\b",
    re.IGNORECASE,
)


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


def _job_state(row: dict) -> dict:
    page = row.get("page") or {}
    sj = page.get("structured_job") or {}
    return {
        "company": row.get("resolved_company") or row.get("company") or sj.get("company") or "",
        "title": row.get("resolved_title") or row.get("title") or sj.get("title") or "",
        "location_strings": row.get("location_strings") or [],
        "is_remote": bool(row.get("is_remote_hint")),
        "title_tag": (page.get("title_tag") or "")[:120],
        "url": (row.get("source_url") or "")[:100],
    }


def _get_rejection_reason(answers: dict) -> str:
    ans = answers.get("rejection_reason")
    if ans and ans.choice in REJECTION_REASONS:
        return ans.choice
    return "NO_MATCH"


def _build_questions(companies: list[str], titles: list[str], locations: list[dict]) -> dict:
    questions: dict = {}

    # Company: NoulQuestion — avoids jev's 255-option cap on ChoiceQuestion.
    # Canonical name is resolved locally via _find_matched_company after the call.
    company_list_text = "\n".join(f"- {name}" for name in companies)
    questions["company"] = NoulQuestion(
        instructions=(
            "Does this job belong to one of the following target companies? "
            "Ignore case, punctuation, legal suffixes (Ltd, plc, Group, Holdings, Corp, UK), "
            "and a leading 'The'. Consider the company name in title_tag, url, and title.\n"
            f"Target companies:\n{company_list_text}"
        ),
        criteria={"true": "Job belongs to a target company", "false": "No target company match"},
    )

    # Titles: one NoulQuestion per target title
    for i, title in enumerate(titles):
        questions[f"title_{i}"] = NoulQuestion(
            instructions=(
                f"Does the job title contain every word from '{title}'? "
                "Word order doesn't matter; ignore case and punctuation; treat trailing 's' as plural."
            ),
            criteria={"true": f"Job title matches '{title}'", "false": f"Job title does NOT match '{title}'"},
        )

    # Locations: one NoulQuestion per target location
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
        questions[f"loc_{i}"] = NoulQuestion(
            instructions=instruction,
            criteria={"true": f"Job is in '{name}'", "false": f"Job is NOT in '{name}'"},
        )

    # Rejection reason: asked alongside match questions for granular SLI tracking
    questions["rejection_reason"] = ChoiceQuestion(
        instructions=(
            "If this job does NOT fully match all three criteria (company + title + location), "
            "what is the single most important reason?"
        ),
        criteria=_REJECTION_CRITERIA,
    )

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
    async with sem:
        try:
            answers = await decide_async(_job_state(row), questions, purpose="job_matching")
        except BudgetExceeded:
            raise
        except Exception as exc:
            log_event(logger, "error", "llm_job_failed", trace_id, error=str(exc), job_id=row.get("job_id"))
            row["META_ERROR_REASON"] = "LLM_ERROR"
            return

    rejection_reason = _get_rejection_reason(answers)

    company_ans = answers.get("company")
    if not company_ans or company_ans.noul <= _MATCH_THRESHOLD:
        reject(row, rejection_reason)
        return
    matched_company = _find_matched_company(_job_state(row)["company"], companies)
    if not matched_company:
        reject(row, rejection_reason)
        return

    matched_titles = [
        titles[i] for i in range(len(titles)) if (a := answers.get(f"title_{i}")) and a.noul > _MATCH_THRESHOLD
    ]
    if not matched_titles:
        reject(row, rejection_reason)
        return

    matched_locs = [
        locations[i]["name"]
        for i in range(len(locations))
        if (a := answers.get(f"loc_{i}")) and a.noul > _MATCH_THRESHOLD
    ]
    if not matched_locs:
        reject(row, rejection_reason)
        return

    row["matched_company"] = matched_company
    row["matched_job_title"] = matched_titles
    row["matched_location"] = matched_locs
    row["reason"] = f"jev: company={matched_company}, titles={matched_titles}, locations={matched_locs}"
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
