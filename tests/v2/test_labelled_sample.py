from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden-dataset"
JOBS_PATH = GOLDEN / "jobs.jsonl"
LABELLED_PATH = GOLDEN / "labelled_300.jsonl"
SEARCH_INPUTS = GOLDEN / "user_search_inputs"

_has_llm_key = bool(
    os.environ.get("AI_GATEWAY_API_KEY") or (Path(".env").exists() and "AI_GATEWAY_API_KEY" in Path(".env").read_text())
)
_requires_llm = pytest.mark.skipif(
    not _has_llm_key,
    reason="No LLM API key — set AI_GATEWAY_API_KEY in .env",
)


# ---------------------------------------------------------------------------
# Dataset sanity checks (no pipeline needed)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def labelled_rows():
    return [json.loads(line) for line in LABELLED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_labelled_dataset_has_expected_shape(labelled_rows):
    assert len(labelled_rows) == 300
    for row in labelled_rows:
        assert "job_id" in row
        assert row["decision"] in ("yes", "no")
        assert "reason" in row


def test_labelled_yes_jobs_count(labelled_rows):
    yes = [r for r in labelled_rows if r["decision"] == "yes"]
    assert len(yes) == 17


def test_labelled_no_jobs_reasons_include_dead_links(labelled_rows):
    # relies on labelled_300.jsonl encoding dead-link rejections as "404/410" in reason
    dead_nos = [r for r in labelled_rows if r["decision"] == "no" and "404/410" in r.get("reason", "")]
    assert len(dead_nos) >= 29


# ---------------------------------------------------------------------------
# Pipeline fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pipeline_results(tmp_path_factory):
    """Run v2 pipeline once on the golden-dataset jobs; return {job_id: row} for all matches."""
    tmp = tmp_path_factory.mktemp("run")
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
def labelled(labelled_rows):
    yes = {r["job_id"] for r in labelled_rows if r["decision"] == "yes"}
    no = {r["job_id"] for r in labelled_rows if r["decision"] == "no"}
    return yes, no


# ---------------------------------------------------------------------------
# Recall and precision tests
# ---------------------------------------------------------------------------


@_requires_llm
def test_recall_meets_target_threshold(pipeline_results, labelled):
    yes_ids, _ = labelled
    hits = yes_ids & pipeline_results.keys()
    assert len(hits) >= 17, f"Recall {len(hits)}/{len(yes_ids)}; misses: {sorted(yes_ids - pipeline_results.keys())}"


@_requires_llm
def test_no_false_positives(pipeline_results, labelled):
    _, no_ids = labelled
    fp = no_ids & pipeline_results.keys()
    assert fp == set(), f"False positives: {sorted(fp)}"


@_requires_llm
def test_matched_fields_present(pipeline_results, labelled):
    yes_ids, _ = labelled
    hits = yes_ids & pipeline_results.keys()
    for jid in hits:
        row = pipeline_results[jid]
        assert row.get("matched_company"), f"{jid}: missing matched_company"
        assert row.get("matched_job_title"), f"{jid}: missing matched_job_title"
        assert row.get("matched_location"), f"{jid}: missing matched_location"
        assert row.get("reason"), f"{jid}: missing reason"
        assert row.get("profile_id") == "a", f"{jid}: wrong profile_id"
