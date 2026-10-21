"""Integration tests for v2 normalization modules."""

from tests.v2.conftest import make_row

# ── resolve_company ──────────────────────────────────────────────────────────


def test_resolve_company_pass_on_match(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp")]
    result = main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["resolved_company"] == "Acme Corp"


def test_resolve_company_rejects_unknown(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    rows = [make_row(company="Unknown Corp XYZ")]
    result = main(ctx, rows)
    assert len(result.data) == 0


def test_resolve_company_uses_structured_job(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_company import main

    ctx["profile"] = profile
    row = make_row(company="Scraped Wrong")
    row["page"] = {"http_status": 200, "structured_job": {"company": "Acme Corp"}}
    result = main(ctx, [row])
    assert len(result.data) == 1
    assert result.data[0]["resolved_company"] == "Acme Corp"


# ── resolve_title ────────────────────────────────────────────────────────────


def test_resolve_title_pass_on_word_match(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    rows = [make_row(title="Senior Controls Engineer")]
    result = main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["resolved_title"] == "Senior Controls Engineer"


def test_resolve_title_rejects_no_overlap(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    rows = [make_row(title="Marketing Director")]
    result = main(ctx, rows)
    assert len(result.data) == 0


def test_resolve_title_structured_job_priority(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    row = make_row(title="Wrong scraped title")
    row["page"] = {"http_status": 200, "structured_job": {"title": "Controls Engineer"}}
    result = main(ctx, [row])
    assert result.data[0]["resolved_title"] == "Controls Engineer"


def test_resolve_title_title_tag_fallback(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_title import main

    ctx["profile"] = profile
    row = make_row(title="Short title")
    row["page"] = {
        "http_status": 200,
        "title_tag": "Senior Electrical Engineer | Acme Corp",
        "structured_job": {},
    }
    result = main(ctx, [row])
    assert "electrical" in result.data[0]["resolved_title"].lower()


# ── resolve_location ─────────────────────────────────────────────────────────


def test_resolve_location_pass_on_city_match(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_location import main

    ctx["profile"] = profile
    rows = [make_row(location="Warrington, United Kingdom")]
    result = main(ctx, rows)
    assert len(result.data) == 1


def test_resolve_location_includes_match(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_location import main

    ctx["profile"] = profile
    rows = [make_row(location="Knutsford, Cheshire")]
    result = main(ctx, rows)
    assert len(result.data) == 1


def test_resolve_location_rejects_unknown_city(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_location import main

    ctx["profile"] = profile
    rows = [make_row(location="Edinburgh, Scotland")]
    result = main(ctx, rows)
    assert len(result.data) == 0


def test_resolve_location_remote_kept_when_profile_has_remote(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_location import main

    ctx["profile"] = profile
    rows = [make_row(location="Remote - UK")]
    result = main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["is_remote_hint"] is True


def test_resolve_location_placeholder_skipped(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_location import main

    ctx["profile"] = profile
    # "2 Locations" placeholder + no structured_job → no usable location strings
    rows = [make_row(location="2 Locations")]
    result = main(ctx, rows)
    assert len(result.data) == 0


def test_resolve_location_reads_sj_additional_locations(ctx, profile):
    from v2.workers.job_matcher.normalization.resolve_location import main

    ctx["profile"] = profile
    row = make_row(location="2 Locations")
    row["page"] = {
        "http_status": 200,
        "structured_job": {"location": "US-TX-Austin", "additional_locations": ["Runcorn"]},
    }
    result = main(ctx, [row])
    assert len(result.data) == 1  # Runcorn is in Warrington includes


# ── filter_dead_links ────────────────────────────────────────────────────────


def test_filter_dead_links_404(ctx, profile):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    ctx["profile"] = profile
    row = make_row()
    row["page"] = {"http_status": 404}
    result = main(ctx, [row])
    assert len(result.data) == 0


def test_filter_dead_links_403_blocked(ctx, profile):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    ctx["profile"] = profile
    row = make_row()
    row["page"] = {"http_status": 403}
    result = main(ctx, [row])
    assert len(result.data) == 0


def test_filter_dead_links_200_passes(ctx, profile):
    from v2.workers.job_matcher.normalization.filter_dead_links import main

    ctx["profile"] = profile
    row = make_row()
    row["page"] = {"http_status": 200, "structured_job": {"title": "Controls Engineer"}}
    result = main(ctx, [row])
    assert len(result.data) == 1
