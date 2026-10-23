"""Unit tests for v2 match_jobs module — helper functions and row-level logic."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

# ── _detect_location_country ────────────────────────────────────────────────


def test_detect_country_us_from_state():
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country(["Warrington, PA, United States"]) == "United States"


def test_detect_country_uk_from_suffix():
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country(["Warrington, United Kingdom"]) == "United Kingdom"


def test_detect_country_empty_returns_empty():
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country([]) == ""


def test_detect_country_latin_foreign_city_returns_empty():
    """Latin-script foreign city without country suffix → unknown; agent decides."""
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country(["Birmingham"]) == ""


# ── _derive_rejection_reason ────────────────────────────────────────────────


def _make_noul_answer(noul: float):
    from v2.shared.api_calls.llm import NoulAnswer

    return NoulAnswer(noul=noul)


def test_derive_rejection_wrong_company():
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {"company": _make_noul_answer(0.1)}
    assert _derive_rejection_reason(answers, [0], 2, ["Warrington"]) == "WRONG_COMPANY"


def test_derive_rejection_wrong_title():
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {"company": _make_noul_answer(0.99), "title_0": _make_noul_answer(0.02)}
    assert _derive_rejection_reason(answers, [0], 2, ["Warrington"]) == "WRONG_TITLE"


def test_derive_rejection_wrong_country():
    """US job: company and title pass but location fails → WRONG_COUNTRY."""
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {
        "company": _make_noul_answer(0.99),
        "title_10": _make_noul_answer(0.98),
    }
    result = _derive_rejection_reason(
        answers,
        asked_title_indices=[10],
        n_locs=12,
        location_strings=["Warrington, PA, United States"],
    )
    assert result == "WRONG_COUNTRY"


def test_derive_rejection_wrong_location_uk_city():
    """UK city not in any profile region → WRONG_LOCATION (not WRONG_COUNTRY)."""
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {
        "company": _make_noul_answer(0.99),
        "title_10": _make_noul_answer(0.98),
    }
    result = _derive_rejection_reason(
        answers,
        asked_title_indices=[10],
        n_locs=12,
        location_strings=["London"],
    )
    assert result == "WRONG_LOCATION"


# ── _relevant_title_indices ─────────────────────────────────────────────────


def test_relevant_titles_exact_match():
    from v2.workers.job_matcher.agent.match_jobs import _relevant_title_indices

    titles = ["Controls Engineer", "Electrical Engineer", "CNC Operator"]
    result = _relevant_title_indices("Controls Engineer", titles)
    assert 0 in result  # "Controls Engineer" shares words
    assert 1 in result  # "Electrical Engineer" shares "engineer"
    assert 2 not in result  # "CNC Operator" shares nothing with "controls engineer"


def test_relevant_titles_no_overlap_excluded():
    from v2.workers.job_matcher.agent.match_jobs import _relevant_title_indices

    titles = ["mig welder", "cnc miller", "paint sprayer"]
    result = _relevant_title_indices("Controls Engineer", titles)
    assert result == []


def test_relevant_titles_plural_stripped():
    """'engineers' should match profile title 'engineer'."""
    from v2.workers.job_matcher.agent.match_jobs import _relevant_title_indices

    titles = ["Electrical Engineer"]
    result = _relevant_title_indices("Senior Electrical Engineers", titles)
    assert 0 in result


# ── _job_state includes location_country ────────────────────────────────────


def test_job_state_includes_location_country():
    from v2.shared.observability.sli_observe import META_OUTCOME
    from v2.workers.job_matcher.agent.match_jobs import _job_state

    row = {
        "job_id": "J001",
        "resolved_company": "Aire Calder",
        "resolved_title": "Controls Engineer",
        "location_strings": ["Warrington, PA, United States"],
        "is_remote_hint": False,
        "source_url": "",
        "page": {},
        META_OUTCOME: "pass",
    }
    state = _job_state(row)
    assert "location_country" in state
    assert state["location_country"] == "United States"


# ── _build_questions: no rejection_reason; no criteria on NoulQuestions ─────


def test_build_questions_no_rejection_reason():
    from v2.workers.job_matcher.agent.match_jobs import _build_questions

    questions = _build_questions(
        companies=[],
        titles=["Controls Engineer"],
        locations=[
            {
                "name": "Warrington",
                "type": "sub_region",
                "includes": [],
                "country": "United Kingdom",
            }
        ],
    )
    assert "rejection_reason" not in questions


def test_noul_questions_have_no_criteria():
    """NoulQuestion instances should have no criteria (or criteria=None) — it's for ChoiceQuestion."""
    from ai.ops.experimental import NoulQuestion

    from v2.workers.job_matcher.agent.match_jobs import _build_questions

    questions = _build_questions(
        companies=[],
        titles=["Controls Engineer", "Electrical Engineer"],
        locations=[
            {
                "name": "Warrington",
                "type": "sub_region",
                "includes": ["Warrington"],
                "country": "United Kingdom",
            }
        ],
    )
    for key, q in questions.items():
        if isinstance(q, NoulQuestion):
            criteria = getattr(q, "criteria", None)
            assert not criteria, f"Question {key!r} has non-empty criteria={criteria!r}"


# ── _job_state: deduplication and url exclusion ──────────────────────────────


def test_job_state_deduplicates_location_strings():
    from v2.shared.observability.sli_observe import META_OUTCOME
    from v2.workers.job_matcher.agent.match_jobs import _job_state

    row = {
        "job_id": "J002",
        "resolved_company": "Aire Calder",
        "resolved_title": "Controls Engineer",
        "location_strings": ["Warrington, PA, United States", "Warrington, PA, United States"],
        "is_remote_hint": False,
        "source_url": "https://feed.example/jobs/s0001435",
        "page": {},
        META_OUTCOME: "pass",
    }
    state = _job_state(row)
    assert state["location_strings"] == ["Warrington, PA, United States"]


def test_job_state_no_url_key():
    """URL is excluded from state because sanitized feed URLs carry no company signal."""
    from v2.shared.observability.sli_observe import META_OUTCOME
    from v2.workers.job_matcher.agent.match_jobs import _job_state

    row = {
        "job_id": "J003",
        "resolved_company": "Aire Calder",
        "resolved_title": "Controls Engineer",
        "location_strings": [],
        "is_remote_hint": False,
        "source_url": "https://feed.example/jobs/s0001435",
        "page": {},
        META_OUTCOME: "pass",
    }
    state = _job_state(row)
    assert "url" not in state


# ── integration: _process_row rejects US job as WRONG_COUNTRY ────────────────


@pytest.fixture
def us_row():
    from tests.v2.conftest import make_row
    from v2.shared.observability.sli_observe import META_OUTCOME

    row = make_row(
        job_id="J_us_001",
        title="Controls Engineer",
        company="Aire Calder",
        location="Warrington, PA, United States",
    )
    row["resolved_company"] = "Aire Calder"
    row["resolved_title"] = "Controls Engineer"
    row["location_strings"] = ["Warrington, PA, United States"]
    row["is_remote_hint"] = False
    row[META_OUTCOME] = "pass"
    return row


@pytest.fixture
def full_profile():
    """Profile with the 'Aire Calder' company and 'Controls Engineer' title."""
    return {
        "profile_id": "test",
        "companies": [{"name": "Aire Calder", "industry": None}],
        "titles": ["Controls Engineer"],
        "locations": [
            {
                "name": "Warrington",
                "type": "sub_region",
                "includes": ["Warrington", "Runcorn"],
                "country": "United Kingdom",
            }
        ],
    }


@pytest.mark.asyncio
async def test_process_row_us_job_rejected_wrong_country(us_row, full_profile, tmp_path, monkeypatch):
    """A US job (company+title match, location=US) must be rejected as WRONG_COUNTRY."""
    from v2.shared.api_calls.llm import NoulAnswer
    from v2.shared.observability.sli_observe import META_OUTCOME, META_REJECTION_REASON
    from v2.workers.job_matcher.agent.match_jobs import _build_questions, _process_row

    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))

    companies = ["Aire Calder"]
    titles = ["Controls Engineer"]
    locations = full_profile["locations"]
    questions = _build_questions(companies, titles, locations)

    # Mock jev: company matches, title matches, all locations fail
    mock_answers = {
        "company": NoulAnswer(noul=0.99),
        "title_0": NoulAnswer(noul=0.98),
        "loc_0": NoulAnswer(noul=0.01),
    }

    sem = asyncio.Semaphore(1)

    with patch(
        "v2.workers.job_matcher.agent.match_jobs.decide_async",
        new=AsyncMock(return_value=mock_answers),
    ):
        await _process_row(sem, us_row, questions, companies, titles, locations, logging.getLogger(), "t")

    assert us_row[META_OUTCOME] == "rejected"
    assert us_row[META_REJECTION_REASON] == "WRONG_COUNTRY"
