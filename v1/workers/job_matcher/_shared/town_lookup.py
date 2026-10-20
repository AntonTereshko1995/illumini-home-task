"""Town lookup: town -> region and country.

Used by resolve_job_town (job side) and match_jobs (profile side). Keys are lower case.
"""

from __future__ import annotations

UK = "United Kingdom"

TOWNS: dict[str, dict[str, str]] = {
    name.lower(): {"town": name, "region": region, "country": UK}
    for region, names in {
        "North West England": [
            "Liverpool",
            "Manchester",
            "Warrington",
            "Salford",
            "Preston",
            "Lancaster",
            "Chester",
            "Bolton",
            "Wigan",
            "Stockport",
            "Runcorn",
            "Widnes",
        ],
        "Yorkshire": ["Leeds", "Sheffield", "York", "Bradford", "Hull"],
        "London": ["London"],
        "West Midlands": ["Birmingham", "Coventry", "Wolverhampton"],
        "East Midlands": ["Derby", "Nottingham", "Leicester"],
        "South West": ["Bristol", "Bath", "Exeter"],
        "Scotland": ["Glasgow", "Edinburgh", "Aberdeen", "Dundee"],
        "Wales": ["Cardiff", "Swansea", "Wrexham"],
        "North East": ["Newcastle", "Sunderland"],
    }.items()
    for name in names
}


def lookup_town(text: str) -> dict[str, str] | None:
    """Exact (case-insensitive) town name -> {"town", "region", "country"}; None when not a known town."""
    return TOWNS.get(text.strip().lower())


def towns_covered(location: dict) -> set[str]:
    """A profile location -> the town names it covers: its own name plus its `includes` list."""
    return {location["name"], *location.get("includes", [])}
