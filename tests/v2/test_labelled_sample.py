"""Integration test: v2 pipeline recall on the hand-labelled 60-job sample.

Requires a live LLM API key (ANTHROPIC_SENIOR_DEVELOPER_KEY or GEMINI_SENIOR_DEVELOPER_KEY).
Skipped automatically in CI / environments without a key.

Target: recall ≥ 8/11 YES jobs, 0 false positives on NO jobs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

LABELLED_PATH = Path("data/labelled_sample.jsonl")
JOBS_PATH = Path("data/jobs_raw.jsonl")
SEARCH_INPUTS = Path("data/user_search_inputs")

_has_llm_key = bool(
    os.environ.get("ANTHROPIC_SENIOR_DEVELOPER_KEY")
    or os.environ.get("GEMINI_SENIOR_DEVELOPER_KEY")
    or (
        Path(".env").exists()
        and any(
            k in Path(".env").read_text() for k in ("ANTHROPIC_SENIOR_DEVELOPER_KEY", "GEMINI_SENIOR_DEVELOPER_KEY")
        )
    )
)
pytestmark = pytest.mark.skipif(not _has_llm_key, reason="No LLM API key — set ANTHROPIC_SENIOR_DEVELOPER_KEY")

KNOWN_MISSES = {"J576140", "J229510", "J809819"}


@pytest.fixture(scope="module")
def pipeline_results(tmp_path_factory):
    """Run v2 pipeline once; return {job_id: matched_row} for all matches."""
    tmp = tmp_path_factory.mktemp("run")
    import os

    os.environ["ILLUMINI_RUNS_DIR"] = str(tmp)
    from v2.workers.job_matcher.handler import run_parallel_pipeline

    run_parallel_pipeline(JOBS_PATH, SEARCH_INPUTS)

    matched: dict[str, dict] = {}
    for jl in tmp.glob("*/*_matched.jsonl"):
        for line in jl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                matched[row["job_id"]] = row
    return matched


@pytest.fixture(scope="module")
def labelled():
    rows = [json.loads(line) for line in LABELLED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    yes = {r["job_id"] for r in rows if r.get("matched_company")}
    no = {r["job_id"] for r in rows if not r.get("matched_company")}
    return yes, no


def test_recall_at_least_8_of_11(pipeline_results, labelled):
    yes_ids, _ = labelled
    hits = yes_ids & pipeline_results.keys()
    assert len(hits) >= 8, f"Recall {len(hits)}/{len(yes_ids)}; misses: {sorted(yes_ids - pipeline_results.keys())}"


def test_no_false_positives(pipeline_results, labelled):
    _, no_ids = labelled
    fp = no_ids & pipeline_results.keys()
    assert fp == set(), f"False positives: {sorted(fp)}"


def test_matched_fields_present(pipeline_results, labelled):
    yes_ids, _ = labelled
    hits = yes_ids & pipeline_results.keys()
    for jid in hits:
        row = pipeline_results[jid]
        assert row.get("matched_company"), f"{jid}: missing matched_company"
        assert row.get("matched_job_title"), f"{jid}: missing matched_job_title"
        assert row.get("matched_location"), f"{jid}: missing matched_location"
        assert row.get("profile_id") == "a", f"{jid}: wrong profile_id"
