"""Parse the job's location string into town/region/country fields.

Stub: exact-match lookup against an inlined TOWNS dict.
TODO: suffix stripping (", UK" / ", United Kingdom"), structured_job fallback,
      address token extraction, remote keyword detection.
"""

from __future__ import annotations

import time

from v2.shared.observability.sli_observe import passed, reject, sli_observe
from v2.shared.patterns.worker_runtime import ExecutionResult

MODULE_NAME = "job_matcher__resolve_location"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"UNKNOWN_LOCATION"}
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()

_UK = "United Kingdom"

_TOWNS: dict[str, dict] = {
    name.lower(): {"town": name, "region": region, "country": _UK}
    for region, names in {
        "North West England": [
            "Liverpool",
            "Manchester",
            "Warrington",
            "Chester",
            "Bolton",
            "Runcorn",
            "Widnes",
            "Salford",
            "Preston",
            "Lancaster",
            "Wigan",
            "Stockport",
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


def _lookup(text: str) -> dict | None:
    return _TOWNS.get(text.strip().lower())


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    """Resolve location string to town/region/country; reject rows that cannot be resolved."""
    trace_id: str = context.get("trace_id")
    start_time = time.time()

    for row in prev_data:
        # TODO: strip ", United Kingdom" / ", UK" suffixes before lookup
        # TODO: parse "N Locations" → consult page.structured_job.locations
        # TODO: detect remote keywords → match remote profile locations
        place = _lookup(row.get("location", ""))
        if place is None:
            reject(row, "UNKNOWN_LOCATION")
            continue
        row.update(town=place["town"], region=place["region"], country=place["country"], used_llm=False)

    kept = passed(prev_data)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{MODULE_NAME}_{trace_id}",
        data=kept,
        artifacts={},
        metrics={},
    )
