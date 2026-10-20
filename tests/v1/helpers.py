from __future__ import annotations

import json
from pathlib import Path

from v1.shared.observability.sli_observe import META_OUTCOME


def make_row(
    job_id: str = "J001",
    title: str = "Controls Engineer",
    company: str = "Acme Corp",
    location: str = "Warrington",
    town: str = "Warrington",
    **kwargs,
) -> dict:
    """Build a minimal normalised row ready for post-normalise modules."""
    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "town": town,
        "salary_gbp": None,
        "source_url": "",
        "page": {},
        META_OUTCOME: "pass",
        **kwargs,
    }


def read_sli(tmp_path: Path, trace_id: str = "t") -> list[dict]:
    """Read SLI events written during a module call."""
    path = tmp_path / trace_id / "sli_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write rows as JSONL for use in load_job_feed tests."""
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
