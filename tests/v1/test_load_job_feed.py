from __future__ import annotations

from tests.v1.helpers import read_sli, write_jsonl
from v1.shared.observability.sli_observe import META_OUTCOME, META_REJECTION_REASON
from v1.workers.job_matcher.modules import load_job_feed


def test_load_job_feed_happy_path(ctx, tmp_path):
    """Valid JSONL: all rows loaded with META_OUTCOME=pass."""
    rows = [{"job_id": "J001", "scraped": {}}, {"job_id": "J002", "scraped": {}}]
    write_jsonl(tmp_path / "jobs.jsonl", rows)
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 2
    assert all(r[META_OUTCOME] == "pass" for r in result.data)


def test_load_job_feed_invalid_json_line_rejected(ctx, tmp_path):
    """Invalid JSON line gets INVALID_JSON rejection; valid lines still load."""
    (tmp_path / "jobs.jsonl").write_text('{"job_id": "J001"}\nnot json\n{"job_id": "J002"}\n', encoding="utf-8")
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 2
    sli = read_sli(tmp_path)
    invalid = [e for e in sli if e.get(META_REJECTION_REASON) == "INVALID_JSON"]
    assert len(invalid) == 1


def test_load_job_feed_non_object_json_rejected(ctx, tmp_path):
    """A JSON array on a line gets NOT_AN_OBJECT."""
    (tmp_path / "jobs.jsonl").write_text('[1,2,3]\n{"job_id": "J001"}\n', encoding="utf-8")
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 1
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "NOT_AN_OBJECT" for e in sli)


def test_load_job_feed_empty_lines_skipped(ctx, tmp_path):
    """Blank lines are ignored."""
    (tmp_path / "jobs.jsonl").write_text('\n\n{"job_id": "J001"}\n\n', encoding="utf-8")
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 1


def test_load_job_feed_empty_file(ctx, tmp_path):
    """Empty file returns empty list."""
    (tmp_path / "jobs.jsonl").write_text("", encoding="utf-8")
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert result.data == []


def test_load_job_feed_sli_written(ctx, tmp_path):
    """SLI events are written for each row."""
    rows = [{"job_id": "J001"}]
    write_jsonl(tmp_path / "jobs.jsonl", rows)
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    load_job_feed.main(ctx, [])
    sli = read_sli(tmp_path)
    assert len(sli) == 1
    assert sli[0]["job_id"] == "J001"


def test_load_job_feed_sli_job_id_for_valid_rows(ctx, tmp_path):
    """SLI events carry the correct job_id for valid rows."""
    rows = [{"job_id": "J999", "scraped": {"title": "T"}}]
    write_jsonl(tmp_path / "jobs.jsonl", rows)
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    load_job_feed.main(ctx, [])
    sli = read_sli(tmp_path)
    assert sli[0]["job_id"] == "J999"
    assert sli[0][META_OUTCOME] == "pass"
