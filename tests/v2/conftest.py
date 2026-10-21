from __future__ import annotations

import pytest


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """Minimal context dict with SLI redirected to tmp_path. trace_id='t'."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    return {"trace_id": "t"}


@pytest.fixture
def profile():
    """Minimal recruiter profile for v2 module tests."""
    return {
        "profile_id": "test",
        "companies": [
            {"name": "Acme Corp", "industry": None},
            {"name": "Siemens Energy", "industry": "Engineering"},
        ],
        "titles": ["Controls Engineer", "Electrical Engineer", "Quality Engineer"],
        "locations": [
            {
                "name": "Warrington",
                "type": "sub_region",
                "includes": ["Warrington", "Runcorn", "Knutsford"],
                "country": "United Kingdom",
            },
            {
                "name": "Remote (UK)",
                "type": "remote",
                "includes": ["Remote", "Home-based"],
                "country": "United Kingdom",
            },
        ],
    }


def make_row(
    job_id: str = "J001",
    title: str = "Controls Engineer",
    company: str = "Acme Corp",
    location: str = "Warrington",
    **kwargs,
) -> dict:
    """Build a minimal v2 row (post-load_job_feed shape)."""
    from v2.shared.observability.sli_observe import META_OUTCOME

    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "salary_gbp": None,
        "source_url": "",
        "page": {"http_status": 200},
        META_OUTCOME: "pass",
        **kwargs,
    }
