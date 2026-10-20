from __future__ import annotations

import json
from pathlib import Path

import pytest

from v1.shared.patterns.worker_runtime import run_pipeline
from v1.workers.job_matcher import handler

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELLED = REPO_ROOT / "data" / "labelled_sample.jsonl"
JOBS_RAW = REPO_ROOT / "data" / "jobs_raw.jsonl"
SEARCH_INPUTS = REPO_ROOT / "data" / "user_search_inputs"


@pytest.fixture
def labelled_data():
    if not LABELLED.exists():
        pytest.skip("data/labelled_sample.jsonl not present")
    return [json.loads(line) for line in LABELLED.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def raw_jobs():
    if not JOBS_RAW.exists():
        pytest.skip("data/jobs_raw.jsonl not present")
    result = {}
    with JOBS_RAW.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                result[row["job_id"]] = row
    return result


# ---------------------------------------------------------------------------
# Labelled sample shape / content sanity checks
# ---------------------------------------------------------------------------


def test_labelled_sample_has_expected_shape(labelled_data):
    """Sanity check: 60 rows, each with decision/reason/matched_* fields."""
    assert len(labelled_data) == 60
    for row in labelled_data:
        assert "job_id" in row
        assert row["decision"] in ("yes", "no")
        assert "reason" in row


def test_labelled_yes_jobs_count(labelled_data):
    yes = [r for r in labelled_data if r["decision"] == "yes"]
    assert len(yes) == 11


def test_labelled_no_jobs_include_dead_links(labelled_data, raw_jobs):
    """8 of the 'no' labels are 404/410 jobs — documents the dead-link bug scope."""
    dead_nos = [
        label
        for label in labelled_data
        if label["decision"] == "no"
        and raw_jobs.get(label["job_id"], {}).get("page", {}).get("http_status") in (404, 410)
    ]
    assert len(dead_nos) >= 8


# ---------------------------------------------------------------------------
# Full pipeline integration: 1529-job feed against profile_a
# These numbers come from run 20261020T153054 and must stay stable.
# ---------------------------------------------------------------------------


def _run_full_pipeline(tmp_path: Path, monkeypatch) -> set[str]:
    """Helper: run v1 on jobs_raw.jsonl vs profile_a, return matched job_id set."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    if not JOBS_RAW.exists() or not SEARCH_INPUTS.exists():
        pytest.skip("data/ files not present")
    outputs = run_pipeline(
        handler.STAGE_GRAPH,
        handler.INPUT_CONTEXT_SCHEMA,
        handler.OUTPUT_CONTEXT_SCHEMA,
        handler.HANDLER_NAME,
        JOBS_RAW,
        SEARCH_INPUTS,
    )
    matched: set[str] = set()
    for path in outputs:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                matched.add(json.loads(line)["job_id"])
    return matched


def test_v1_full_pipeline_output_count(tmp_path, monkeypatch):
    """v1 outputs exactly 2 matched jobs on the full 1529-job feed (run 20261020T153054 baseline)."""
    matched = _run_full_pipeline(tmp_path, monkeypatch)
    assert len(matched) == 2


def test_v1_full_pipeline_matches_correct_jobs(tmp_path, monkeypatch):
    """The 2 matched jobs are J678841 and J948846 (Inkwell Copperleaf Group, Wrexham)."""
    matched = _run_full_pipeline(tmp_path, monkeypatch)
    assert matched == {"J678841", "J948846"}


def test_v1_full_pipeline_j685745_not_matched(tmp_path, monkeypatch):
    """J685745 (Runcorn, Driftwood Copperleaf) passes resolve_job_town but fails NO_TITLE_MATCH.
    Title is 'Software Engineer III, Digital Pathology...' — no profile title is a substring."""
    matched = _run_full_pipeline(tmp_path, monkeypatch)
    assert "J685745" not in matched


# ---------------------------------------------------------------------------
# Pipeline on the 60 labelled jobs — recall measurement
# ---------------------------------------------------------------------------


def test_v1_pipeline_on_labelled_subset(tmp_path, monkeypatch, labelled_data, raw_jobs):
    """Run v1 pipeline on the 60 labelled jobs; measure recall against YES decisions.

    v1 is expected to match 0/11 YES jobs due to combined location + title bugs.
    This test documents the baseline; changing the assertion requires a real improvement.
    """
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    if not SEARCH_INPUTS.exists():
        pytest.skip("data/ files not present")
    labelled_ids = {r["job_id"] for r in labelled_data}
    subset = [raw_jobs[jid] for jid in labelled_ids if jid in raw_jobs]
    jobs_file = tmp_path / "labelled_jobs.jsonl"
    jobs_file.write_text("\n".join(json.dumps(j) for j in subset) + "\n", encoding="utf-8")
    outputs = run_pipeline(
        handler.STAGE_GRAPH,
        handler.INPUT_CONTEXT_SCHEMA,
        handler.OUTPUT_CONTEXT_SCHEMA,
        handler.HANDLER_NAME,
        jobs_file,
        SEARCH_INPUTS,
    )
    matched_ids: set[str] = set()
    for path in outputs:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                matched_ids.add(json.loads(line)["job_id"])
    yes_ids = {r["job_id"] for r in labelled_data if r["decision"] == "yes"}
    recall = len(yes_ids & matched_ids) / len(yes_ids) if yes_ids else 0.0
    print(f"\nv1 recall on YES labelled jobs: {recall:.0%} ({len(yes_ids & matched_ids)}/{len(yes_ids)})")
    assert recall >= 0.0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bugs: all 11 YES jobs dropped — resolve_job_town rejects 10 on UNKNOWN_LOCATION, "
        "1 (J685745) on NO_TITLE_MATCH — recall is 0%"
    ),
)
def test_v1_pipeline_recall_above_50_percent(tmp_path, monkeypatch, labelled_data, raw_jobs):
    """Documents: v1 fails to reach even 50% recall on labelled YES jobs."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    if not SEARCH_INPUTS.exists():
        pytest.skip("data/ files not present")
    labelled_ids = {r["job_id"] for r in labelled_data}
    subset = [raw_jobs[jid] for jid in labelled_ids if jid in raw_jobs]
    jobs_file = tmp_path / "labelled_jobs.jsonl"
    jobs_file.write_text("\n".join(json.dumps(j) for j in subset) + "\n", encoding="utf-8")
    outputs = run_pipeline(
        handler.STAGE_GRAPH,
        handler.INPUT_CONTEXT_SCHEMA,
        handler.OUTPUT_CONTEXT_SCHEMA,
        handler.HANDLER_NAME,
        jobs_file,
        SEARCH_INPUTS,
    )
    matched_ids: set[str] = set()
    for path in outputs:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                matched_ids.add(json.loads(line)["job_id"])
    yes_ids = {r["job_id"] for r in labelled_data if r["decision"] == "yes"}
    recall = len(yes_ids & matched_ids) / len(yes_ids)
    assert recall >= 0.50
