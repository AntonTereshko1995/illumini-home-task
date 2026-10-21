"""Shared golden-dataset fixtures for v2 normalization tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from v2.shared.observability.sli_observe import META_OUTCOME

_GOLDEN_DIR = Path("tests/v2/golden-dataset")
_JOBS_PATH = _GOLDEN_DIR / "jobs.jsonl"
_LABELS_PATH = _GOLDEN_DIR / "labelled_300.jsonl"
_SEARCH_INPUTS = _GOLDEN_DIR / "user_search_inputs"


def fresh_rows(rows: list[dict]) -> list[dict]:
    """Shallow-copy rows and reset META_OUTCOME='pass' for a clean module run."""
    out = [r.copy() for r in rows]
    for r in out:
        r[META_OUTCOME] = "pass"
    return out


def _raw_to_row(raw: dict) -> dict:
    scraped = raw.get("scraped") or {}
    return {
        "job_id": raw["job_id"],
        "title": scraped.get("title", "").strip(),
        "company": scraped.get("company", "").strip(),
        "location": scraped.get("location", "").strip(),
        "salary_gbp": None,
        "source_url": raw.get("source_url", ""),
        "page": raw.get("page") or {},
        META_OUTCOME: "pass",
    }


@pytest.fixture(scope="module")
def golden_rows():
    """All 300 golden-dataset jobs converted to v2 row shape."""
    raws = [json.loads(line) for line in _JOBS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [_raw_to_row(r) for r in raws]


@pytest.fixture(scope="module")
def labels():
    """Dict {job_id: label_dict} for all 300 labelled jobs."""
    return {
        json.loads(line)["job_id"]: json.loads(line)
        for line in _LABELS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


@pytest.fixture(scope="module")
def profile_a():
    """Real profile_a loaded from golden-dataset user_search_inputs/."""
    from v2.shared.patterns.worker_runtime import load_search_inputs

    return dict(load_search_inputs(_SEARCH_INPUTS))["profile_a"]


@pytest.fixture(scope="module")
def yes_ids(labels):
    """Frozenset of job_ids labelled 'yes' (18 jobs)."""
    return frozenset(jid for jid, lbl in labels.items() if lbl["decision"] == "yes")


@pytest.fixture(scope="module")
def dead_link_ids(labels):
    """Jobs whose label reason mentions '404' or '410' (29 jobs)."""
    return frozenset(
        jid for jid, lbl in labels.items() if "404" in lbl.get("reason", "") or "410" in lbl.get("reason", "")
    )


@pytest.fixture
def gctx(tmp_path, monkeypatch, profile_a):
    """Function-scoped context: real profile_a + SLI redirected to tmp_path."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    return {"trace_id": "golden", "profile": profile_a}
