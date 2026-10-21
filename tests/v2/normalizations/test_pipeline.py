"""End-to-end tests for the full v2 normalization pipeline (all 5 stages)."""

from __future__ import annotations

from tests.v2.normalizations.conftest import fresh_rows


def test_full_pipeline_preserves_yes_jobs(gctx, golden_rows, yes_ids):
    """All 5 stages run sequentially — all YES jobs except known misses must survive."""
    from v2.workers.job_matcher.normalization import (
        filter_dead_links,
        filter_duplicates,
        normalise_location,
        resolve_company,
        resolve_title,
    )

    data = fresh_rows(golden_rows)
    for module in [filter_dead_links, filter_duplicates, normalise_location, resolve_title, resolve_company]:
        data = module.main(gctx, data).data

    passed_ids = {r["job_id"] for r in data}
    expected_ids = yes_ids
    missed = expected_ids - passed_ids
    assert not missed, (
        f"YES jobs lost in full normalization pipeline: {sorted(missed)}\n"
        "Check which stage rejects them via sli_events.jsonl."
    )


def test_full_pipeline_reduces_feed_size(gctx, golden_rows, yes_ids):
    """Normalization must reject at least some jobs — it is not a no-op."""
    from v2.workers.job_matcher.normalization import (
        filter_dead_links,
        filter_duplicates,
        normalise_location,
        resolve_company,
        resolve_title,
    )

    data = fresh_rows(golden_rows)
    for module in [filter_dead_links, filter_duplicates, normalise_location, resolve_title, resolve_company]:
        data = module.main(gctx, data).data

    expected_yes = len(yes_ids)
    assert len(data) < len(golden_rows), "Normalization must reject at least some of the 300 jobs"
    assert len(data) >= expected_yes, (
        f"Normalization over-filtered: only {len(data)} rows remain but {expected_yes} YES jobs should survive"
    )
