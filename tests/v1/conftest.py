from __future__ import annotations

import pytest


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """Minimal context dict with SLI redirected to tmp_path. trace_id='t'."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    return {"trace_id": "t"}


@pytest.fixture
def profile():
    """Minimal recruiter profile for testing match_jobs and portal_matches_output."""
    return {
        "profile_id": "test",
        "companies": [{"name": "Acme Corp", "industry": None}],
        "titles": ["Controls Engineer", "Electrical Engineer"],
        "locations": [
            {
                "name": "Warrington",
                "type": "sub_region",
                "includes": ["Warrington", "Runcorn"],
                "country": "United Kingdom",
            }
        ],
    }
