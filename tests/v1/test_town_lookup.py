from __future__ import annotations

from v1.workers.job_matcher._shared.town_lookup import lookup_town, towns_covered


def test_lookup_town_known_city():
    assert lookup_town("Warrington") == {
        "town": "Warrington",
        "region": "North West England",
        "country": "United Kingdom",
    }


def test_lookup_town_case_insensitive():
    assert lookup_town("warrington")["town"] == "Warrington"


def test_lookup_town_with_whitespace():
    assert lookup_town(" Liverpool ")["town"] == "Liverpool"


def test_lookup_town_unknown_returns_none():
    assert lookup_town("Atlantis") is None


def test_lookup_town_empty_string_returns_none():
    assert lookup_town("") is None


def test_lookup_town_wrexham():
    result = lookup_town("Wrexham")
    assert result is not None
    assert result["town"] == "Wrexham"
    assert result["region"] == "Wales"


def test_lookup_town_chester():
    result = lookup_town("Chester")
    assert result is not None
    assert result["region"] == "North West England"


def test_lookup_town_runcorn():
    result = lookup_town("Runcorn")
    assert result is not None
    assert result["town"] == "Runcorn"


def test_towns_covered_includes_own_name():
    loc = {"name": "Warrington", "type": "sub_region", "includes": ["Runcorn"]}
    assert "Warrington" in towns_covered(loc)


def test_towns_covered_includes_list_members():
    loc = {"name": "Warrington", "type": "sub_region", "includes": ["Runcorn", "Widnes"]}
    assert towns_covered(loc) == {"Warrington", "Runcorn", "Widnes"}


def test_towns_covered_no_includes_key():
    loc = {"name": "London", "type": "city"}
    assert towns_covered(loc) == {"London"}


def test_towns_covered_remote_location():
    loc = {"name": "Remote (UK)", "type": "remote", "includes": ["Remote", "Home-based", "Work from home"]}
    assert towns_covered(loc) == {"Remote (UK)", "Remote", "Home-based", "Work from home"}


def test_towns_covered_empty_includes():
    loc = {"name": "Birmingham", "type": "city", "includes": []}
    assert towns_covered(loc) == {"Birmingham"}
