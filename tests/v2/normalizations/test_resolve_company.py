"""Tests for v2 normalization module: resolve_company."""

from __future__ import annotations

from tests.v2.conftest import make_row
from tests.v2.normalizations.conftest import fresh_rows


def test_exact_match_passes(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    result = main(ctx, [make_row(company="Acme Corp")])
    assert len(result.data) == 1
    assert result.data[0]["resolved_company"] == "Acme Corp"


def test_unknown_company_rejected(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(company="Unknown Corp XYZ")]).data) == 0


def test_structured_job_overrides_scraped(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    row = make_row(company="Scraped Wrong")
    row["page"] = {"http_status": 200, "structured_job": {"company": "Acme Corp"}}
    result = main(ctx, [row])
    assert len(result.data) == 1
    assert result.data[0]["resolved_company"] == "Acme Corp"


def test_legal_suffix_stripped(ctx, profile):
    """'Siemens Energy Ltd' matches profile entry 'Siemens Energy' after 'Ltd' is stripped."""
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(company="Siemens Energy Ltd")]).data) == 1


def test_sets_resolved_company_on_kept_row(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp")]
    main(ctx, rows)
    assert rows[0]["resolved_company"] == "Acme Corp"


def test_sli_company_not_in_profile_reason(ctx, profile, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    main(ctx, [make_row(company="Unknown Corp XYZ")])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "COMPANY_NOT_IN_PROFILE" for e in sli)


# ── golden dataset ────────────────────────────────────────────────────────────


def test_golden_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    """All YES jobs (except known misses) must survive resolve_company."""
    from v2.workers.job_matcher.normalization.resolve_company import main

    assertable_ids = yes_ids
    rows = [r for r in fresh_rows(golden_rows) if r["job_id"] in assertable_ids]
    result = main(gctx, rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = assertable_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected: {sorted(rejected)}"
