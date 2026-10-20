from __future__ import annotations

import pytest

from tests.v1.helpers import make_row, read_sli
from v1.shared.observability.sli_observe import META_REJECTION_REASON
from v1.workers.job_matcher.modules import match_jobs
from v1.workers.job_matcher.modules.match_jobs import matched_locations, matched_titles

# ---------------------------------------------------------------------------
# matched_titles — pure function tests
# ---------------------------------------------------------------------------


def test_matched_titles_substring_found():
    """v1 matches when profile title is a substring of job title."""
    assert matched_titles("Senior Controls Engineer", ["Controls Engineer"]) == ["Controls Engineer"]


def test_matched_titles_no_match():
    assert matched_titles("Accountant", ["Controls Engineer"]) == []


def test_matched_titles_multiple_profile_titles_partial_match():
    result = matched_titles("Senior Controls Engineer", ["Controls Engineer", "Electrical Engineer"])
    assert result == ["Controls Engineer"]


def test_matched_titles_all_match():
    # "Senior Controls Engineer Electrical": "Controls Engineer" is a substring; "Electrical Engineer" is not
    result = matched_titles("Senior Controls Engineer Electrical", ["Controls Engineer", "Electrical Engineer"])
    assert "Controls Engineer" in result


def test_matched_titles_empty_titles_list():
    assert matched_titles("Controls Engineer", []) == []


def test_matched_titles_empty_job_title():
    assert matched_titles("", ["Controls Engineer"]) == []


@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: matched_titles is case-sensitive — 'controls engineer' != 'Controls Engineer'",
)
def test_matched_titles_case_insensitive():
    assert matched_titles("controls engineer", ["Controls Engineer"]) == ["Controls Engineer"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: matched_titles uses substring, not word-by-word — 'Quality Engineer' not found "
        "in 'Quality and Warranty Engineer' even though all words are present"
    ),
)
def test_matched_titles_non_adjacent_words():
    """Spec: every word of profile title must appear in job title in any order."""
    assert matched_titles("Quality and Warranty Engineer", ["Quality Engineer"]) == ["Quality Engineer"]


@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: matched_titles is case-sensitive — 'cnc miller' never matches 'CNC Miller'",
)
def test_matched_titles_lowercase_profile_title():
    assert matched_titles("CNC Miller", ["cnc miller"]) == ["cnc miller"]


# ---------------------------------------------------------------------------
# Real feed titles — parameterized to document every concrete v1 miss
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "job_title,profile_title",
    [
        ("Business Development Manager", "business development manager"),
        ("Business Development Manager - North", "business development manager"),
        ("CNC Turner Setter/Programmer (West Byfleet)", "cnc turner"),
    ],
)
@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: matched_titles is case-sensitive — real feed uses title-case, profile has lowercase entries",
)
def test_matched_titles_case_real_feed(job_title, profile_title):
    """Real feed titles where only case prevents the match."""
    assert matched_titles(job_title, [profile_title]) == [profile_title]


@pytest.mark.parametrize(
    "job_title,profile_title",
    [
        ("Engineer - Electrical (Rail Depot)", "Electrical Engineer"),
        ("Sr. Applications Engineer - Electrical", "Electrical Engineer"),
        ("PSV / HGV Engineer (Mechanical and Electrical)", "Electrical Engineer"),
        ("PSV / HGV Engineer (Mechanical and Electrical)", "Mechanical Engineer"),
        ("Manufacturing Services Technician - Electrician", "Manufacturing Technician"),
        ("Principal Engineer - Product Safety", "Product Engineer"),
        ("Highways Engineer – Design - (Area Manager Role)", "Design Engineer"),
    ],
)
@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: matched_titles uses substring — misses real feed titles where profile words "
        "are present but not adjacent (40 jobs in feed affected)"
    ),
)
def test_matched_titles_word_order_real_feed(job_title, profile_title):
    """Real feed titles where all profile words are present but not consecutive."""
    assert matched_titles(job_title, [profile_title]) == [profile_title]


# ---------------------------------------------------------------------------
# matched_locations — pure function tests
# ---------------------------------------------------------------------------


def test_matched_locations_exact_town():
    locations = [{"name": "Warrington", "type": "sub_region", "includes": ["Warrington", "Runcorn"], "country": "UK"}]
    assert matched_locations("Warrington", locations) == ["Warrington"]


def test_matched_locations_town_in_includes():
    locations = [{"name": "Warrington", "type": "sub_region", "includes": ["Warrington", "Runcorn"], "country": "UK"}]
    assert matched_locations("Runcorn", locations) == ["Warrington"]


def test_matched_locations_no_match():
    locations = [{"name": "Warrington", "type": "sub_region", "includes": ["Warrington"], "country": "UK"}]
    assert matched_locations("London", locations) == []


def test_matched_locations_empty_list():
    assert matched_locations("Warrington", []) == []


# ---------------------------------------------------------------------------
# match_jobs.main() — module tests
# ---------------------------------------------------------------------------


def test_match_jobs_all_three_pass(ctx, profile):
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Controls Engineer", town="Warrington")]
    result = match_jobs.main(ctx, rows)
    assert len(result.data) == 1
    row = result.data[0]
    assert row["matched_company"] == "Acme Corp"
    assert "Controls Engineer" in row["matched_job_title"]
    assert "Warrington" in row["matched_location"]
    assert row["reason"]


def test_match_jobs_company_not_in_profile(ctx, profile):
    ctx["profile"] = profile
    rows = [make_row(company="Unknown Corp")]
    result = match_jobs.main(ctx, rows)
    assert len(result.data) == 0


def test_match_jobs_sli_company_not_listed(ctx, profile, tmp_path):
    ctx["profile"] = profile
    rows = [make_row(company="Unknown Corp")]
    match_jobs.main(ctx, rows)
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "COMPANY_NOT_LISTED" for e in sli)


def test_match_jobs_no_title_match(ctx, profile):
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Accountant")]
    result = match_jobs.main(ctx, rows)
    assert len(result.data) == 0


def test_match_jobs_sli_no_title_match(ctx, profile, tmp_path):
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Accountant")]
    match_jobs.main(ctx, rows)
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "NO_TITLE_MATCH" for e in sli)


def test_match_jobs_no_location_match(ctx, profile):
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Controls Engineer", town="London")]
    result = match_jobs.main(ctx, rows)
    assert len(result.data) == 0


def test_match_jobs_sli_no_location_match(ctx, profile, tmp_path):
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Controls Engineer", town="London")]
    match_jobs.main(ctx, rows)
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "NO_LOCATION_MATCH" for e in sli)


def test_match_jobs_runcorn_in_includes(ctx, profile):
    """Runcorn is in Warrington includes — should match Warrington location."""
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Controls Engineer", town="Runcorn")]
    result = match_jobs.main(ctx, rows)
    assert len(result.data) == 1
    assert "Warrington" in result.data[0]["matched_location"]


def test_match_jobs_empty_input(ctx, profile):
    ctx["profile"] = profile
    result = match_jobs.main(ctx, [])
    assert result.data == []


def test_match_jobs_reason_field_format(ctx, profile):
    """reason field follows the pattern 'title at company, in town'."""
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Controls Engineer", town="Warrington")]
    result = match_jobs.main(ctx, rows)
    assert result.data[0]["reason"] == "Controls Engineer at Acme Corp, in Warrington"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "v1 bug: company matching is exact — 'Cobalt Zephyr Holdings' != profile entry "
        "'Cobalt Zephyr' (legal suffix not stripped)"
    ),
)
def test_match_jobs_company_legal_suffix_stripped(ctx):
    """Profile has 'Cobalt Zephyr'; job has 'Cobalt Zephyr Holdings' — should match after suffix stripping."""
    profile = {
        "profile_id": "t",
        "companies": [{"name": "Cobalt Zephyr"}],
        "titles": ["CM engineer"],
        "locations": [{"name": "Warrington", "type": "city", "includes": ["Warrington"], "country": "UK"}],
    }
    ctx["profile"] = profile
    rows = [make_row(company="Cobalt Zephyr Holdings", title="CM engineer", town="Warrington")]
    result = match_jobs.main(ctx, rows)
    assert len(result.data) == 1
