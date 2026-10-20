from __future__ import annotations

import pytest

from tests.v1.helpers import read_sli
from v1.workers.job_matcher.modules import normalise_job_rows
from v1.workers.job_matcher.modules.normalise_job_rows import parse_salary

# ---------------------------------------------------------------------------
# parse_salary — pure function tests
# ---------------------------------------------------------------------------


def test_parse_salary_gbp_format():
    assert parse_salary("£45,000") == 45000


def test_parse_salary_plain_integer_string():
    assert parse_salary("45000") == 45000


def test_parse_salary_none_returns_none():
    assert parse_salary(None) is None


def test_parse_salary_empty_string_returns_none():
    assert parse_salary("") is None


def test_parse_salary_zero():
    assert parse_salary("£0") == 0


def test_parse_salary_with_commas():
    assert parse_salary("100,000") == 100000


@pytest.mark.xfail(strict=True, reason="v1 bug: parse_salary crashes on '£50K per Annum' — int() can't parse 'K'")
def test_parse_salary_k_suffix():
    result = parse_salary("£50K per Annum")
    assert result is not None


@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: parse_salary crashes on '1K - 3K per Annum' — int() can't parse range with K suffix",
)
def test_parse_salary_range_with_k():
    result = parse_salary("1K - 3K per Annum")
    assert result is not None


@pytest.mark.parametrize(
    "salary_str",
    [
        "£31K per Annum",  # K suffix, different amount
        "2 - 3 per Annum",  # numeric range, no currency
        "15 - 17 per Annum",  # numeric range
        "$2 per Annum",  # USD symbol — int("$2 per Annum") raises
        "00-14",  # ambiguous hyphenated format
    ],
)
@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: parse_salary raises ValueError on non-integer salary strings present in real feed",
)
def test_parse_salary_real_feed_formats(salary_str):
    """Real salary strings from jobs_raw.jsonl that crash parse_salary in v1."""
    _ = parse_salary(salary_str)  # should not raise


# ---------------------------------------------------------------------------
# normalise_job_rows.main() — module tests
# ---------------------------------------------------------------------------


def test_normalise_extracts_scraped_fields(ctx):
    raw = [
        {
            "job_id": "J001",
            "scraped": {
                "title": " Controls Engineer ",
                "company": " Acme ",
                "location": " Warrington ",
                "salary": None,
            },
        }
    ]
    result = normalise_job_rows.main(ctx, raw)
    assert len(result.data) == 1
    row = result.data[0]
    assert row["title"] == "Controls Engineer"
    assert row["company"] == "Acme"
    assert row["location"] == "Warrington"
    assert row["salary_gbp"] is None
    assert row["job_id"] == "J001"


def test_normalise_preserves_page(ctx):
    raw = [
        {
            "job_id": "J001",
            "scraped": {"title": "T", "company": "C", "location": "L"},
            "page": {"http_status": 200, "title_tag": "T | C"},
        }
    ]
    result = normalise_job_rows.main(ctx, raw)
    assert result.data[0]["page"]["http_status"] == 200


def test_normalise_salary_parsed(ctx):
    raw = [{"job_id": "J001", "scraped": {"title": "T", "company": "C", "location": "L", "salary": "£45,000"}}]
    result = normalise_job_rows.main(ctx, raw)
    assert result.data[0]["salary_gbp"] == 45000


def test_normalise_empty_input(ctx):
    result = normalise_job_rows.main(ctx, [])
    assert result.data == []


def test_normalise_source_url_preserved(ctx):
    raw = [
        {
            "job_id": "J001",
            "scraped": {"title": "T", "company": "C", "location": "L"},
            "source_url": "https://example.com/job/1",
        }
    ]
    result = normalise_job_rows.main(ctx, raw)
    assert result.data[0]["source_url"] == "https://example.com/job/1"


def test_normalise_missing_source_url_defaults_to_empty(ctx):
    raw = [{"job_id": "J001", "scraped": {"title": "T", "company": "C", "location": "L"}}]
    result = normalise_job_rows.main(ctx, raw)
    assert result.data[0]["source_url"] == ""


@pytest.mark.xfail(
    strict=True,
    reason="v1 bug: row with missing 'scraped' key is silently dropped — no SLI entry written",
)
def test_normalise_missing_scraped_has_sli_entry(ctx, tmp_path):
    """Missing 'scraped' key is caught by bare except; the row should have a SLI entry but doesn't."""
    raw = [{"job_id": "J001"}]
    normalise_job_rows.main(ctx, raw)
    sli = read_sli(tmp_path)
    assert any(e["job_id"] == "J001" for e in sli)
