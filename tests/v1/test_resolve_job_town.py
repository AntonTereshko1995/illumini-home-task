from __future__ import annotations

import pytest

from tests.v1.helpers import make_row, read_sli
from v1.shared.observability.sli_observe import META_REJECTION_REASON
from v1.workers.job_matcher.modules import resolve_job_town


def test_resolve_known_town(ctx):
    rows = [make_row(location="Warrington")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    row = result.data[0]
    assert row["town"] == "Warrington"
    assert row["region"] == "North West England"
    assert row["country"] == "United Kingdom"
    assert row["used_llm"] is False


def test_resolve_case_insensitive(ctx):
    rows = [make_row(location="warrington")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["town"] == "Warrington"


def test_resolve_unknown_location_rejected(ctx):
    rows = [make_row(location="Unknown City XYZ")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 0


def test_resolve_sli_marks_unknown_location(ctx, tmp_path):
    rows = [make_row(location="Unknown City XYZ")]
    resolve_job_town.main(ctx, rows)
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "UNKNOWN_LOCATION" for e in sli)


def test_resolve_empty_location_rejected(ctx):
    rows = [make_row(location="")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 0


def test_resolve_runcorn_known(ctx):
    """Runcorn is in TOWNS dict — resolves successfully."""
    rows = [make_row(location="Runcorn")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["town"] == "Runcorn"


def test_resolve_wrexham_known(ctx):
    """Wrexham is in TOWNS dict (Wales) — resolves successfully."""
    rows = [make_row(location="Wrexham")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["town"] == "Wrexham"
    assert result.data[0]["region"] == "Wales"


def test_resolve_mixed_batch(ctx):
    """Known towns pass; unknown are rejected. Only known rows come back."""
    rows = [
        make_row(job_id="J001", location="Warrington"),
        make_row(job_id="J002", location="Unknown City XYZ"),
        make_row(job_id="J003", location="Liverpool"),
    ]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 2
    ids = {r["job_id"] for r in result.data}
    assert ids == {"J001", "J003"}


def test_resolve_funnel_baseline(ctx):
    """Wrexham, Chester, and Runcorn are bare city names in TOWNS dict — all must resolve without regression."""
    for loc in ["Wrexham", "Chester", "Runcorn"]:
        rows = [make_row(location=loc)]
        result = resolve_job_town.main(ctx, rows)
        assert len(result.data) == 1, f"{loc!r} should resolve but does not"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: 'Birmingham, United Kingdom' fails exact lookup — country suffix not stripped "
        "(555 jobs in real feed use this format)"
    ),
)
def test_resolve_location_with_country_suffix(ctx):
    rows = [make_row(location="Birmingham, United Kingdom")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["town"] == "Birmingham"


@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: 'Crewe' not in TOWNS dict — common UK city missing from lookup table",
)
def test_resolve_crewe_not_in_towns(ctx):
    rows = [make_row(location="Crewe")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: '2 Locations' placeholder not resolved — structured_job.locations never "
        "consulted (337 jobs in real feed)"
    ),
)
def test_resolve_location_placeholder_fallback(ctx):
    """'2 Locations' placeholder should fall back to structured_job.locations."""
    rows = [
        make_row(
            location="2 Locations",
            page={"structured_job": {"locations": ["Manchester, United Kingdom"]}},
        )
    ]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: 'Bolton, GB' fails exact lookup — country-code suffix not stripped "
        "(12 jobs in real feed use this pattern)"
    ),
)
def test_resolve_location_with_gb_suffix(ctx):
    """'Bolton, GB' is the City,GB format — 12 jobs in the real feed use this pattern."""
    rows = [make_row(location="Bolton, GB")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1


@pytest.mark.parametrize(
    "location,expected_town",
    [
        ("Derby, Derbyshire, United Kingdom", "Derby"),
        ("Chester, Cheshire, United Kingdom", "Chester"),
        ("Bradford, West Yorkshire, United Kingdom", "Bradford"),
        ("Birmingham, Warwickshire, United Kingdom", "Birmingham"),
        ("Glasgow, Glasgow City, United Kingdom", "Glasgow"),
    ],
)
@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: 'City, Region, Country' three-part format not handled — "
        "suffix stripping must also remove the county layer (54 fixable jobs in real feed)"
    ),
)
def test_resolve_three_part_location(ctx, location, expected_town):
    """Real feed uses 'City, County, United Kingdom' — stripping suffix + county should resolve the city."""
    rows = [make_row(location=location)]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["town"] == expected_town


@pytest.mark.parametrize(
    "location",
    [
        "Hybrid - 2 days Warrington",
        "Remote - UK",
    ],
)
@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: hybrid/remote location strings not parsed — embedded city or remote flag never extracted",
)
def test_resolve_hybrid_remote_formats(ctx, location):
    """Hybrid and remote strings from real feed that contain resolvable location info."""
    rows = [make_row(location=location)]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1


@pytest.mark.parametrize(
    "location",
    [
        "Birmingham, AL, United States",
        "Chester, PA, United States",
    ],
)
def test_resolve_foreign_country_correctly_rejected(ctx, location):
    """US locations are rejected — correct outcome even though v1 rejects via UNKNOWN_LOCATION
    rather than an explicit country check."""
    rows = [make_row(location=location)]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 0
