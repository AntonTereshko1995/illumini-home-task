"""Tests for v2 normalization module: filter_duplicates."""

from __future__ import annotations

from tests.v2.conftest import make_row
from tests.v2.normalizations.conftest import fresh_rows


def test_unique_ids_all_kept(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main

    rows = [make_row(job_id="J001"), make_row(job_id="J002", title="Electrical Engineer")]
    assert len(main(ctx, rows).data) == 2


def test_same_id_first_kept(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main

    rows = [make_row(job_id="J001"), make_row(job_id="J001", title="Electrical Engineer")]
    result = main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["title"] == "Controls Engineer"  # first row wins


def test_three_same_only_first_kept(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main

    rows = [make_row(job_id="J001"), make_row(job_id="J001"), make_row(job_id="J001")]
    assert len(main(ctx, rows).data) == 1


def test_empty_input(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main

    assert main(ctx, []).data == []


def test_mixed_batch_keeps_unique_rejects_dupe(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main

    rows = [
        make_row(job_id="J001"),
        make_row(job_id="J002", title="Electrical Engineer"),
        make_row(job_id="J001", title="Quality Engineer"),  # duplicate of J001
    ]
    result = main(ctx, rows)
    assert len(result.data) == 2
    assert {r["job_id"] for r in result.data} == {"J001", "J002"}


def test_sli_marks_duplicate(ctx, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.filter_duplicates import main

    rows = [make_row(job_id="J001"), make_row(job_id="J001")]
    main(ctx, rows)
    sli = read_sli(tmp_path)
    dupes = [e for e in sli if e.get(META_REJECTION_REASON) == "DUPLICATE"]
    assert len(dupes) == 1


# ── golden dataset ────────────────────────────────────────────────────────────


def test_golden_all_jobs_have_unique_ids(gctx, golden_rows):
    """Golden dataset must have no duplicate job_ids — dedup stage is a no-op."""
    from v2.workers.job_matcher.normalization.filter_duplicates import main

    result = main(gctx, fresh_rows(golden_rows))
    assert len(result.data) == len(golden_rows), (
        f"Unexpected duplicates in golden dataset: {len(golden_rows) - len(result.data)} rows dropped"
    )
