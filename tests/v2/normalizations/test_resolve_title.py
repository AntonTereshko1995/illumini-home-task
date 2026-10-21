"""Tests for v2 normalization module: resolve_title."""

from __future__ import annotations

from tests.v2.conftest import make_row
from tests.v2.normalizations.conftest import fresh_rows


def test_word_match_passes(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    result = main(ctx, [make_row(title="Senior Controls Engineer")])
    assert len(result.data) == 1
    assert result.data[0]["resolved_title"] == "Senior Controls Engineer"


def test_no_overlap_rejected(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(title="Marketing Director")]).data) == 0


def test_structured_job_priority(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    row = make_row(title="Wrong scraped title")
    row["page"] = {"http_status": 200, "structured_job": {"title": "Controls Engineer"}}
    assert main(ctx, [row]).data[0]["resolved_title"] == "Controls Engineer"


def test_title_tag_fallback(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    row = make_row(title="Short title")
    row["page"] = {
        "http_status": 200,
        "title_tag": "Senior Electrical Engineer | Acme Corp",
        "structured_job": {},
    }
    assert "electrical" in main(ctx, [row]).data[0]["resolved_title"].lower()


def test_h1_fallback_matches_profile(ctx, profile):
    """h1 is used when no structured_job.title and no title_tag are present."""
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    row = make_row(title="Wrong scraped")
    row["page"] = {"http_status": 200, "h1": "Electrical Engineer", "structured_job": {}}
    result = main(ctx, [row])
    assert len(result.data) == 1
    assert result.data[0]["resolved_title"] == "Electrical Engineer"


def test_plural_word_matches(ctx, profile):
    """'Controls Engineers' — trailing 's' stripped — still matches 'Controls Engineer'."""
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(title="Controls Engineers")]).data) == 1


def test_sets_resolved_title_on_kept_row(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    rows = [make_row(title="Controls Engineer")]
    main(ctx, rows)
    assert rows[0]["resolved_title"] == "Controls Engineer"


def test_sli_title_not_in_profile_reason(ctx, profile, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    main(ctx, [make_row(title="Marketing Director")])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "TITLE_NOT_IN_PROFILE" for e in sli)


# ── golden dataset ────────────────────────────────────────────────────────────


def test_golden_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    """All YES jobs (except known misses) must survive resolve_title."""
    from v2.workers.job_matcher.normalization.resolve_title import main

    assertable_ids = yes_ids
    rows = [r for r in fresh_rows(golden_rows) if r["job_id"] in assertable_ids]
    result = main(gctx, rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = assertable_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected: {sorted(rejected)}"
