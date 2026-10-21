"""Tests for v2 normalization module: normalise_location."""

from __future__ import annotations

from tests.v2.conftest import make_row
from tests.v2.normalizations.conftest import fresh_rows


def test_uk_city_passes(ctx, profile):
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(location="Warrington, United Kingdom")]).data) == 1


def test_uk_city_no_country_suffix_passes(ctx, profile):
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(location="Knutsford, Cheshire")]).data) == 1


def test_non_latin_script_rejected(ctx, profile):
    """Non-Latin script in location strings is unambiguously non-UK → reject."""
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(location="東京都千代田区")]).data) == 0


def test_latin_foreign_city_passes(ctx, profile):
    """Latin-script foreign city (e.g. wrong structured data) is NOT rejected here — agent decides."""
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(location="Birmingham, AL, United States")]).data) == 1


def test_ambiguous_location_passes(ctx, profile):
    """No sj.* location data and no country signal in page → keep (agent decides)."""
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    assert len(main(ctx, [make_row(location="2 Locations")]).data) == 1


def test_remote_kept_when_profile_has_remote(ctx, profile):
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    result = main(ctx, [make_row(location="Remote - UK")])
    assert len(result.data) == 1
    assert result.data[0]["is_remote_hint"] is True


def test_sj_additional_locations(ctx, profile):
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    row = make_row(location="2 Locations")
    row["page"] = {
        "http_status": 200,
        "structured_job": {"location": "US-TX-Austin", "additional_locations": ["Runcorn"]},
    }
    assert len(main(ctx, [row]).data) == 1


def test_sj_locations_array(ctx, profile):
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    row = make_row(location="2 Locations")
    row["page"] = {"http_status": 200, "structured_job": {"locations": ["Warrington, UK", "London"]}}
    assert len(main(ctx, [row]).data) == 1


def test_sets_location_strings_and_remote_hint(ctx, profile):
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    rows = [make_row(location="Warrington")]
    main(ctx, rows)
    assert "location_strings" in rows[0]
    assert rows[0]["is_remote_hint"] is False


def test_sli_non_latin_rejection_reason(ctx, profile, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    main(ctx, [make_row(location="東京都千代田区")])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "LOCATION_NOT_IN_PROFILE" for e in sli)


def test_sj_location_with_uk_code_passes(ctx, profile):
    """Job with placeholder scraped.location but Latin sj.location passes."""
    from v2.workers.job_matcher.normalization.normalise_location import main

    ctx["profile"] = profile
    row = make_row(location="2 Locations")
    row["page"] = {
        "http_status": 200,
        "structured_job": {"location": "Derby - Moor Lane (UK-EM)", "additional_locations": ["Bristol"]},
    }
    assert len(main(ctx, [row]).data) == 1


# ── golden dataset ────────────────────────────────────────────────────────────


def test_golden_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    """All YES jobs must survive normalise_location."""
    from v2.workers.job_matcher.normalization.normalise_location import main

    rows = [r for r in fresh_rows(golden_rows) if r["job_id"] in yes_ids]
    result = main(gctx, rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = yes_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected: {sorted(rejected)}"
