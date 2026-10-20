from __future__ import annotations

import pytest

from tests.v1.helpers import make_row, read_sli
from v1.shared.observability.sli_observe import META_REJECTION_REASON
from v1.workers.job_matcher.modules import drop_duplicate_jobs
from v1.workers.job_matcher.modules.drop_duplicate_jobs import dedupe_key


def test_dedup_unique_rows_all_kept(ctx):
    rows = [make_row(job_id="J001"), make_row(job_id="J002", title="Electrical Engineer")]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 2


def test_dedup_duplicate_title_company_second_rejected(ctx):
    rows = [make_row(job_id="J001"), make_row(job_id="J002")]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["job_id"] == "J001"


def test_dedup_three_duplicates_only_first_kept(ctx):
    rows = [make_row(job_id=f"J00{i}") for i in range(3)]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 1


def test_dedup_different_companies_both_kept(ctx):
    rows = [
        make_row(job_id="J001", company="Acme Corp"),
        make_row(job_id="J002", company="Beta Ltd"),
    ]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 2


def test_dedup_different_titles_both_kept(ctx):
    rows = [
        make_row(job_id="J001", title="Controls Engineer"),
        make_row(job_id="J002", title="Electrical Engineer"),
    ]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 2


def test_dedup_key_is_title_pipe_company():
    """Documents the current (buggy) key format: title|company, not job_id."""
    row = make_row(job_id="J001", title="Controls Engineer", company="Acme")
    assert dedupe_key(row) == "Controls Engineer|Acme"


def test_dedup_sli_marks_duplicates(ctx, tmp_path):
    rows = [make_row(job_id="J001"), make_row(job_id="J002")]
    drop_duplicate_jobs.main(ctx, rows)
    sli = read_sli(tmp_path)
    dupes = [e for e in sli if e.get(META_REJECTION_REASON) == "DUPLICATE"]
    assert len(dupes) == 1 and dupes[0]["job_id"] == "J002"


def test_dedup_empty_input(ctx):
    result = drop_duplicate_jobs.main(ctx, [])
    assert result.data == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: dedup key is title|company, not job_id — two jobs at same company "
        "with same title but different locations are incorrectly merged"
    ),
)
def test_dedup_different_job_ids_same_title_company_both_kept(ctx):
    """Two genuine different jobs (different locations, different job_ids) at same company with same title."""
    rows = [
        make_row(job_id="J001", location="Warrington", town="Warrington"),
        make_row(job_id="J002", location="Manchester", town="Manchester"),
    ]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 2
