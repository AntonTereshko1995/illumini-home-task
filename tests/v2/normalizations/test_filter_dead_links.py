"""Tests for v2 normalization module: filter_dead_links."""

from __future__ import annotations

from tests.v2.conftest import make_row
from tests.v2.normalizations.conftest import fresh_rows


def test_404_rejected(ctx):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 404}
    assert len(main(ctx, [row]).data) == 0


def test_410_rejected(ctx):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 410}
    assert len(main(ctx, [row]).data) == 0


def test_403_blocked(ctx):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 403}
    assert len(main(ctx, [row]).data) == 0


def test_405_blocked(ctx):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 405}
    assert len(main(ctx, [row]).data) == 0


def test_200_with_structured_job_passes(ctx, profile):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    ctx["profile"] = profile
    row = make_row()
    row["page"] = {"http_status": 200, "structured_job": {"title": "Controls Engineer"}}
    assert len(main(ctx, [row]).data) == 1


def test_200_no_content_rejected(ctx):
    """200 with no structured_job title, no h1, no sj company → BLOCKED_PAGE."""
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 200, "h1": None, "structured_job": {}}
    assert len(main(ctx, [row]).data) == 0


def test_200_h1_only_passes(ctx):
    """200 with a non-empty h1 but no structured_job → verifiable, kept."""
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 200, "h1": "Controls Engineer", "structured_job": {}}
    assert len(main(ctx, [row]).data) == 1


def test_sli_dead_link_reason(ctx, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 404}
    main(ctx, [row])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "DEAD_LINK" for e in sli)


def test_sli_blocked_page_reason(ctx, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    row = make_row()
    row["page"] = {"http_status": 403}
    main(ctx, [row])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "BLOCKED_PAGE" for e in sli)


# ── golden dataset ────────────────────────────────────────────────────────────


def test_golden_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    """All YES jobs (except known misses) must survive filter_dead_links."""
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    assertable_ids = yes_ids
    rows = [r for r in fresh_rows(golden_rows) if r["job_id"] in assertable_ids]
    result = main(gctx, rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = assertable_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected: {sorted(rejected)}"


def test_golden_rejects_all_dead_link_labelled_jobs(gctx, golden_rows, dead_link_ids):
    """Every job labelled '404/410 dead' must be caught by filter_dead_links."""
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    rows = [r for r in fresh_rows(golden_rows) if r["job_id"] in dead_link_ids]
    result = main(gctx, rows)
    passed_ids = {r["job_id"] for r in result.data}
    still_passing = dead_link_ids & passed_ids
    assert not still_passing, f"Dead-link jobs not rejected: {sorted(still_passing)}"
