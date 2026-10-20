"""Golden check: v1 passes this today, and a good change keeps it passing. No network, no LLM spend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from v1.shared.patterns.worker_runtime import run_pipeline
from v1.workers.job_matcher import handler

GOLDEN = Path(__file__).resolve().parent.parent / "data" / "golden"
REQUIRED = {"job_id", "profile_id", "matched_company", "matched_job_title", "matched_location", "reason", "used_llm"}


def test_golden_feed_matches_listed_company_title_and_town(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    outputs = run_pipeline(
        handler.STAGE_GRAPH,
        handler.INPUT_CONTEXT_SCHEMA,
        handler.OUTPUT_CONTEXT_SCHEMA,
        handler.HANDLER_NAME,
        GOLDEN / "jobs_small.jsonl",
        GOLDEN / "user_search_inputs",
    )
    ((path, count),) = outputs.items()
    rows = {r["job_id"]: r for r in map(json.loads, Path(path).read_text(encoding="utf-8").splitlines())}
    assert Path(path).name == "profile_golden_matched.jsonl" and count == "2"
    assert set(rows) == {"G000001", "G000002"}
    assert rows["G000001"]["matched_company"] == "Golden Fixture Ltd"
    assert rows["G000001"]["matched_job_title"] == ["Controls Engineer"]
    assert rows["G000001"]["matched_location"] == ["Warrington"]
    for row in rows.values():
        assert REQUIRED <= row.keys()
        assert row["profile_id"] == "golden" and row["matched_job_title"] and row["matched_location"] and row["reason"]
