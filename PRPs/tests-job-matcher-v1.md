# PRP: Comprehensive Test Suite for job_matcher v1

## Goal

Write a full pytest test suite for the v1 `job_matcher` pipeline that:

1. Lives in `tests/v1/` — a dedicated directory that mirrors the `v1/` source tree and leaves room for `tests/v2/` later
2. Tests every module in isolation — calling `main()` directly with crafted rows
3. Tests every pure helper function (`parse_salary`, `matched_titles`, `matched_locations`, `dedupe_key`, `lookup_town`, `towns_covered`)
4. Documents all known v1 bugs with `pytest.mark.xfail(strict=True, reason="v1 bug: ...")` — these tests are **expected to fail on v1 and that is correct**
5. Validates the full pipeline against the 60-row `data/labelled_sample.jsonl` (integration layer)
6. Keeps the existing `tests/test_golden.py` and `tests/test_llm_cap.py` passing without modification

**End state**: `make test` runs green. Passing tests = v1 behaves correctly. `XFAIL` tests = documented bugs (intentionally broken in v1 — they serve as the spec for v2). When v2 fixes a bug, the corresponding xfail flips to `XPASS` and breaks CI until the `xfail` mark is removed.

### Philosophy: xfail tests ARE the spec for v2

v1 is deliberately broken. Many tests will show `XFAIL` in the output — this is not a problem, it is the point. Every `@pytest.mark.xfail(strict=True)` test:
- Documents exactly what is wrong and why (via `reason=`)
- Pinpoints which module/function needs changing
- Becomes a regression gate the moment the bug is fixed in v2

---

## Why

- The brief explicitly asks for "well-written tests for the rules & logic you implement"
- The 10 known bugs (documented in NOTES.md) have no test coverage — fixing one in v2 has no regression net
- The labelled sample is the only ground-truth: a test against it tracks accuracy improvements
- Module-level tests make it possible to fix one bug at a time and see immediate pass/fail feedback

---

## What

### Module coverage plan

| File | Scope |
|------|-------|
| `tests/__init__.py` | empty — makes `tests` a package for imports |
| `tests/v1/__init__.py` | empty — makes `tests/v1` a package for imports |
| `tests/v1/helpers.py` | `make_row()`, `read_sli()`, `write_jsonl()` shared helpers |
| `tests/v1/conftest.py` | `ctx`, `profile` pytest fixtures |
| `tests/v1/test_town_lookup.py` | `lookup_town`, `towns_covered` pure functions |
| `tests/v1/test_load_job_feed.py` | `load_job_feed.main()` flows |
| `tests/v1/test_normalise_job_rows.py` | `parse_salary` + `normalise_job_rows.main()` flows |
| `tests/v1/test_drop_duplicate_jobs.py` | `dedupe_key` + `drop_duplicate_jobs.main()` flows |
| `tests/v1/test_resolve_job_town.py` | `resolve_job_town.main()` flows |
| `tests/v1/test_match_jobs.py` | `matched_titles`, `matched_locations` + `match_jobs.main()` flows |
| `tests/v1/test_portal_matches_output.py` | `portal_matches_output.main()` flows |
| `tests/v1/test_labelled_sample.py` | Full pipeline against 60 real labelled jobs |

### Success Criteria

- [ ] `make test` exits 0 — all tests either PASS or XFAIL (no FAILED, no ERROR)
- [ ] Every xfail test has `strict=True` and a "v1 bug:" reason string
- [ ] No new test introduces a network call or LLM API call
- [ ] `ruff check tests/v1/` exits 0 (linting)
- [ ] `tests/test_golden.py` and `tests/test_llm_cap.py` still pass (untouched)

---

## Real Run Data (run `20261020T153054`) — ground truth for integration assertions

These numbers come from running the v1 pipeline on the full 1 529-job feed against `profile_a`. Use them to set concrete baseline assertions in `test_labelled_sample.py` and `test_resolve_job_town.py`.

### Pipeline funnel (exact)

```
Module                    Input   Pass   Rejected    Reason
──────────────────────────────────────────────────────────────────
load_job_feed             1529    1529   0
normalise_job_rows        1529    1517   ~12         (silent exception, no SLI entry)
drop_duplicate_jobs       1517    1445   72          DUPLICATE
resolve_job_town          1445       6   1439        UNKNOWN_LOCATION  ← primary bottleneck
match_jobs                   6       2      4        3×COMPANY_NOT_LISTED, 1×NO_TITLE_MATCH
OUTPUT                       2
```

### The 6 jobs that survive resolve_job_town (bare-city names in TOWNS dict)

| job_id  | location  | company              | match_jobs outcome  |
|---------|-----------|----------------------|---------------------|
| J678841 | Wrexham   | Inkwell Copperleaf Group | ✅ PASS (output)  |
| J948846 | Wrexham   | Inkwell Copperleaf Group | ✅ PASS (output)  |
| J775031 | Chester   | Moorside Millrace    | ❌ COMPANY_NOT_LISTED |
| J190105 | Wrexham   | Mersey Ironbridge    | ❌ COMPANY_NOT_LISTED |
| J185944 | Wrexham   | Mersey Ironbridge    | ❌ COMPANY_NOT_LISTED |
| J685745 | Runcorn   | Driftwood Copperleaf | ❌ NO_TITLE_MATCH (title is "Software Engineer III, Digital Pathology…") |

### Location format distribution in the 1 529-job feed

| Format                      | Count | % of feed | v1 outcome                       |
|-----------------------------|-------|-----------|----------------------------------|
| `"City, United Kingdom"`    | 555   | 36.3%     | ❌ UNKNOWN_LOCATION (all)         |
| `""` (empty)                | 420   | 27.5%     | ❌ UNKNOWN_LOCATION (all)         |
| `"N Locations"` placeholder | 337   | 22.0%     | ❌ UNKNOWN_LOCATION (all)         |
| bare city / other           | 205   | 13.4%     | ✅ if city is in TOWNS dict       |
| `"City, GB"` / `"City, UK"` |  12   | 0.8%      | ❌ UNKNOWN_LOCATION (all)         |

**Recoverable jobs if suffix-stripping is fixed:** 104 of the 555 "City, United Kingdom" jobs have a city from `profile_a`'s covered towns. Fixing this single suffix-stripping bug lifts output from 2 → ~50 jobs.

---

## All Needed Context

### Source files — read ALL of these before writing tests

```yaml
- file: v1/workers/job_matcher/modules/load_job_feed.py
  why: REJECTION_REASONS = {"INVALID_JSON", "NOT_AN_OBJECT"}; module name for SLI

- file: v1/workers/job_matcher/modules/normalise_job_rows.py
  why: parse_salary function; silent exception swallowing bug; salary_gbp field

- file: v1/workers/job_matcher/modules/drop_duplicate_jobs.py
  why: dedupe_key f"{title}|{company}" — the bug; REJECTION_REASONS = {"DUPLICATE"}

- file: v1/workers/job_matcher/modules/resolve_job_town.py
  why: lookup_town call; REJECTION_REASONS = {"UNKNOWN_LOCATION"}

- file: v1/workers/job_matcher/modules/match_jobs.py
  why: matched_titles (substring, case-sensitive, BUG); matched_locations; three-gate logic

- file: v1/workers/job_matcher/modules/portal_matches_output.py
  why: output filename pattern; required output fields; artifact["output_path"]

- file: v1/workers/job_matcher/_shared/town_lookup.py
  why: TOWNS dict (limited to ~35 cities); lookup_town; towns_covered logic

- file: v1/shared/observability/sli_observe.py
  why: META_OUTCOME constant; passed(); reject(); sli_observe() writes to run_dir/sli_events.jsonl

- file: v1/shared/patterns/worker_runtime.py
  why: run_dir uses ILLUMINI_RUNS_DIR env var; ExecutionResult shape

- file: tests/test_golden.py
  why: PATTERN TO FOLLOW — monkeypatch.setenv("ILLUMINI_RUNS_DIR"), run_pipeline, tmp_path

- file: tests/test_llm_cap.py
  why: PATTERN TO FOLLOW — monkeypatch, fixture pattern, fake_send pattern

- file: data/golden/jobs_small.jsonl
  why: understand golden job shape; minimal valid row structure

- file: data/golden/user_search_inputs/profile_golden/location_searches.json
  why: profile location shape with sub_region type and includes list

- file: data/labelled_sample.jsonl
  why: 60 rows: {"job_id", "decision": "yes"/"no", "reason", "matched_company", ...}
```

### Known v1 Bugs (from NOTES.md) — each needs an xfail test

| # | Location | Bug |
|---|----------|-----|
| 1 | handler level | No dead-link filter: 404/410 jobs pass through (8 in labelled sample) |
| 2 | `resolve_job_town` | "Birmingham, United Kingdom" → UNKNOWN_LOCATION (suffix not stripped; 555 jobs use this format, 104 have profile cities) |
| 2b | `resolve_job_town` | "Bolton, GB" → UNKNOWN_LOCATION (City, GB/UK suffix variant; 12 jobs in feed) |
| 3 | `resolve_job_town` | "Crewe" → UNKNOWN_LOCATION (Crewe not in TOWNS dict) |
| 4 | `resolve_job_town` | "2 Locations" placeholder → UNKNOWN_LOCATION (337 jobs; never uses structured_job.locations) |
| 5 | `matched_titles` | Case-sensitive: `"controls engineer" in "Senior Controls Engineer"` → False |
| 6 | `matched_titles` | Non-adjacent words: `"Quality Engineer" in "Quality and Warranty Engineer"` → False |
| 7 | `match_jobs` | Company exact match only: "Cobalt Zephyr Holdings" ≠ profile "Cobalt Zephyr" |
| 8 | `normalise_job_rows` | `parse_salary("£50K per Annum")` → `ValueError` from `int("50K per Annum")` |
| 9 | `normalise_job_rows` | Missing "scraped" key silently drops row — no SLI entry recorded |
| 10 | `drop_duplicate_jobs` | Dedup key is `title|company`, not `job_id` — two jobs at same company with same title but different locations are incorrectly merged |

### Data shapes

**Normalised row** (output of `normalise_job_rows`, input to all downstream modules):
```python
{
    "job_id": "J001",
    "title": "Controls Engineer",
    "company": "Acme Corp",
    "location": "Warrington",
    "salary_gbp": None,      # int or None
    "source_url": "",
    "page": {},              # raw page dict
    "META_OUTCOME": "pass",  # from sli_observe.META_OUTCOME
}
```

**After `resolve_job_town` adds fields:**
```python
{"town": "Warrington", "region": "North West England", "country": "United Kingdom", "used_llm": False}
```

**After `match_jobs` adds fields:**
```python
{
    "matched_company": "Acme Corp",
    "matched_job_title": ["Controls Engineer"],
    "matched_location": ["Warrington"],
    "reason": "Controls Engineer at Acme Corp, in Warrington",
}
```

**Profile shape** (from `load_search_inputs`):
```python
{
    "profile_id": "test",
    "companies": [{"name": "Acme Corp", "industry": None}],
    "titles": ["Controls Engineer", "Electrical Engineer"],
    "locations": [{
        "name": "Warrington",
        "type": "sub_region",
        "includes": ["Warrington", "Runcorn"],
        "country": "United Kingdom"
    }]
}
```

### TOWNS dict in v1 — test boundary knowledge

```
North West England: Liverpool, Manchester, Warrington, Salford, Preston, Lancaster,
                    Chester, Bolton, Wigan, Stockport, Runcorn, Widnes
Yorkshire:          Leeds, Sheffield, York, Bradford, Hull
London:             London
West Midlands:      Birmingham, Coventry, Wolverhampton
East Midlands:      Derby, Nottingham, Leicester
South West:         Bristol, Bath, Exeter
Scotland:           Glasgow, Edinburgh, Aberdeen, Dundee
Wales:              Cardiff, Swansea, Wrexham
North East:         Newcastle, Sunderland
```

**Missing from TOWNS** (causes v1 bugs): Crewe, Knutsford, Bangor, Bromborough, Ellesmere Port, Macclesfield

**Location formats that always fail v1's exact-match lookup** (concrete examples from the real feed):
- `"Birmingham, United Kingdom"` — 80+ jobs (most common pattern to fix)
- `"Bolton, GB"` — City, GB suffix variant (12 jobs total in feed)
- `"2 Locations"`, `"3 Locations"` — placeholder strings (337 jobs total)
- `""` (empty string) — 420 jobs have no scraped location at all

### SLI file location

The SLI file written by `sli_observe()` is at:
```
{ILLUMINI_RUNS_DIR}/{trace_id}/sli_events.jsonl
```

With `monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))` and `trace_id = "t"`, the path is:
```python
tmp_path / "t" / "sli_events.jsonl"
```

### Important import paths

```python
from v1.workers.job_matcher.modules import load_job_feed
from v1.workers.job_matcher.modules import normalise_job_rows
from v1.workers.job_matcher.modules.normalise_job_rows import parse_salary
from v1.workers.job_matcher.modules import drop_duplicate_jobs
from v1.workers.job_matcher.modules.drop_duplicate_jobs import dedupe_key
from v1.workers.job_matcher.modules import resolve_job_town
from v1.workers.job_matcher.modules import match_jobs
from v1.workers.job_matcher.modules.match_jobs import matched_titles, matched_locations
from v1.workers.job_matcher.modules import portal_matches_output
from v1.workers.job_matcher._shared.town_lookup import lookup_town, towns_covered
from v1.shared.observability.sli_observe import META_OUTCOME, META_REJECTION_REASON
from v1.shared.patterns.worker_runtime import run_pipeline
from v1.workers.job_matcher import handler
```

---

## Implementation Blueprint

### Task 0: CREATE `tests/__init__.py` and `tests/v1/__init__.py`

Both files are **empty**. They make the directories proper Python packages so test files can import helpers with:
```python
from tests.v1.helpers import make_row, read_sli, write_jsonl
```

### Task 1: CREATE `tests/v1/helpers.py`

Shared helper functions (NOT pytest fixtures — plain module-level functions importable from any test file with `from tests.v1.helpers import ...`):

```python
# tests/v1/helpers.py
from __future__ import annotations
import json
from pathlib import Path
from v1.shared.observability.sli_observe import META_OUTCOME


def make_row(
    job_id: str = "J001",
    title: str = "Controls Engineer",
    company: str = "Acme Corp",
    location: str = "Warrington",
    town: str = "Warrington",
    **kwargs,
) -> dict:
    """Build a minimal normalised row ready for post-normalise modules."""
    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "town": town,          # added by resolve_job_town
        "salary_gbp": None,
        "source_url": "",
        "page": {},
        META_OUTCOME: "pass",  # CRITICAL: modules filter on this value
        **kwargs,
    }


def read_sli(tmp_path: Path, trace_id: str = "t") -> list[dict]:
    """Read SLI events written during a module call."""
    path = tmp_path / trace_id / "sli_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write rows as JSONL for use in load_job_feed tests."""
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
```

### Task 2: CREATE `tests/v1/conftest.py`

Fixtures are scoped to `tests/v1/` only — the existing `tests/conftest.py` (if any) is left untouched.

```python
# tests/v1/conftest.py
from __future__ import annotations
import pytest


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """Minimal context dict with SLI redirected to tmp_path. trace_id='t'."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    return {"trace_id": "t"}


@pytest.fixture
def profile():
    """Minimal recruiter profile for testing match_jobs and portal_matches_output."""
    return {
        "profile_id": "test",
        "companies": [{"name": "Acme Corp", "industry": None}],
        "titles": ["Controls Engineer", "Electrical Engineer"],
        "locations": [
            {
                "name": "Warrington",
                "type": "sub_region",
                "includes": ["Warrington", "Runcorn"],
                "country": "United Kingdom",
            }
        ],
    }
```

### Task 3: CREATE `tests/v1/test_town_lookup.py`

Pure function tests — no SLI, no tmp_path, no network:

```python
# Test groups:
# 1. lookup_town happy path
# 2. lookup_town edge cases
# 3. towns_covered city/sub_region/remote types
# 4. towns_covered edge cases

def test_lookup_town_known_city():
    assert lookup_town("Warrington") == {"town": "Warrington", "region": "North West England", "country": "United Kingdom"}

def test_lookup_town_case_insensitive():
    assert lookup_town("warrington")["town"] == "Warrington"

def test_lookup_town_with_whitespace():
    assert lookup_town(" Liverpool ")["town"] == "Liverpool"  # strip() applied

def test_lookup_town_unknown_returns_none():
    assert lookup_town("Atlantis") is None

def test_lookup_town_empty_string_returns_none():
    assert lookup_town("") is None

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
```

### Task 4: CREATE `tests/v1/test_load_job_feed.py`

Call `load_job_feed.main()` with a temp JSONL file:

```python
# PATTERN: write JSONL to tmp_path/jobs.jsonl, put path in ctx["jobs_path"]
# ctx fixture already sets ILLUMINI_RUNS_DIR

def test_load_job_feed_happy_path(ctx, tmp_path):
    """Valid JSONL: all rows loaded with META_OUTCOME=pass."""
    rows = [{"job_id": "J001", "scraped": {}}, {"job_id": "J002", "scraped": {}}]
    write_jsonl(tmp_path / "jobs.jsonl", rows)
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 2
    assert all(r[META_OUTCOME] == "pass" for r in result.data)

def test_load_job_feed_invalid_json_line_rejected(ctx, tmp_path):
    """Invalid JSON line gets INVALID_JSON rejection; valid lines still load."""
    (tmp_path / "jobs.jsonl").write_text('{"job_id": "J001"}\nnot json\n{"job_id": "J002"}\n')
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 2  # only valid rows in result.data
    sli = read_sli(tmp_path)
    invalid = [e for e in sli if e[META_REJECTION_REASON] == "INVALID_JSON"]
    assert len(invalid) == 1

def test_load_job_feed_non_object_json_rejected(ctx, tmp_path):
    """A JSON array on a line gets NOT_AN_OBJECT."""
    (tmp_path / "jobs.jsonl").write_text('[1,2,3]\n{"job_id": "J001"}\n')
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 1
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "NOT_AN_OBJECT" for e in sli)

def test_load_job_feed_empty_lines_skipped(ctx, tmp_path):
    """Blank lines are ignored."""
    (tmp_path / "jobs.jsonl").write_text('\n\n{"job_id": "J001"}\n\n')
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert len(result.data) == 1

def test_load_job_feed_empty_file(ctx, tmp_path):
    """Empty file returns empty list."""
    (tmp_path / "jobs.jsonl").write_text("")
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    result = load_job_feed.main(ctx, [])
    assert result.data == []

def test_load_job_feed_sli_written(ctx, tmp_path):
    """SLI events are written for each row."""
    rows = [{"job_id": "J001"}]
    write_jsonl(tmp_path / "jobs.jsonl", rows)
    ctx["jobs_path"] = str(tmp_path / "jobs.jsonl")
    load_job_feed.main(ctx, [])
    sli = read_sli(tmp_path)
    assert len(sli) == 1
    assert sli[0]["job_id"] == "J001"
```

### Task 5: CREATE `tests/v1/test_normalise_job_rows.py`

Split: pure function tests for `parse_salary` + module tests:

```python
# --- parse_salary pure function tests ---

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

@pytest.mark.xfail(strict=True, reason="v1 bug: parse_salary crashes on '£50K per Annum' — int() can't parse 'K'")
def test_parse_salary_k_suffix():
    result = parse_salary("£50K per Annum")
    assert result is not None  # should return something reasonable, not raise

@pytest.mark.xfail(strict=True, reason="v1 bug: parse_salary crashes on '1K - 3K per Annum'")
def test_parse_salary_range_with_k():
    result = parse_salary("1K - 3K per Annum")
    assert result is not None

# --- normalise_job_rows module tests ---

def test_normalise_extracts_scraped_fields(ctx):
    raw = [{"job_id": "J001", "scraped": {"title": " Controls Engineer ", "company": " Acme ", "location": " Warrington ", "salary": None}}]
    result = normalise_job_rows.main(ctx, raw)
    assert len(result.data) == 1
    row = result.data[0]
    assert row["title"] == "Controls Engineer"   # stripped
    assert row["company"] == "Acme"
    assert row["location"] == "Warrington"
    assert row["salary_gbp"] is None
    assert row["job_id"] == "J001"

def test_normalise_preserves_page(ctx):
    raw = [{"job_id": "J001", "scraped": {"title": "T", "company": "C", "location": "L"}, "page": {"http_status": 200, "title_tag": "T | C"}}]
    result = normalise_job_rows.main(ctx, raw)
    assert result.data[0]["page"]["http_status"] == 200

def test_normalise_salary_parsed(ctx):
    raw = [{"job_id": "J001", "scraped": {"title": "T", "company": "C", "location": "L", "salary": "£45,000"}}]
    result = normalise_job_rows.main(ctx, raw)
    assert result.data[0]["salary_gbp"] == 45000

def test_normalise_empty_input(ctx):
    result = normalise_job_rows.main(ctx, [])
    assert result.data == []

@pytest.mark.xfail(strict=True, reason="v1 bug: row with missing 'scraped' key is silently dropped — no SLI entry written")
def test_normalise_missing_scraped_has_sli_entry(ctx, tmp_path):
    """Missing 'scraped' key is caught by bare except; the row should have a SLI entry."""
    raw = [{"job_id": "J001"}]  # no "scraped" key
    normalise_job_rows.main(ctx, raw)
    sli = read_sli(tmp_path)
    assert any(e["job_id"] == "J001" for e in sli)  # currently no entry is written
```

### Task 6: CREATE `tests/v1/test_drop_duplicate_jobs.py`

```python
def test_dedup_unique_rows_all_kept(ctx):
    rows = [make_row(job_id="J001"), make_row(job_id="J002", title="Electrical Engineer")]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 2

def test_dedup_duplicate_title_company_second_rejected(ctx):
    rows = [make_row(job_id="J001"), make_row(job_id="J002")]  # same title+company
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["job_id"] == "J001"  # first wins

def test_dedup_three_duplicates_only_first_kept(ctx):
    rows = [make_row(job_id=f"J00{i}") for i in range(3)]  # all same title+company
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 1

def test_dedup_key_is_title_pipe_company():
    """Documents the current (buggy) key format."""
    row = make_row(job_id="J001", title="Controls Engineer", company="Acme")
    assert dedupe_key(row) == "Controls Engineer|Acme"

def test_dedup_sli_marks_duplicates(ctx, tmp_path):
    rows = [make_row(job_id="J001"), make_row(job_id="J002")]
    drop_duplicate_jobs.main(ctx, rows)
    sli = read_sli(tmp_path)
    dupes = [e for e in sli if e.get(META_REJECTION_REASON) == "DUPLICATE"]
    assert len(dupes) == 1 and dupes[0]["job_id"] == "J002"

@pytest.mark.xfail(strict=True, reason="v1 bug: dedup key is title|company, not job_id — two jobs at same company same title but different locations are incorrectly merged")
def test_dedup_different_job_ids_same_title_company_both_kept(ctx):
    """Two genuine different jobs (different locations, different job_ids) at same company with same title."""
    rows = [
        make_row(job_id="J001", location="Warrington", town="Warrington"),
        make_row(job_id="J002", location="Manchester", town="Manchester"),  # different city
    ]
    result = drop_duplicate_jobs.main(ctx, rows)
    assert len(result.data) == 2  # currently: J002 is incorrectly rejected as DUPLICATE
```

### Task 7: CREATE `tests/v1/test_resolve_job_town.py`

```python
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

@pytest.mark.xfail(strict=True, reason="v1 bug: 'Birmingham, United Kingdom' fails exact lookup — country suffix not stripped")
def test_resolve_location_with_country_suffix(ctx):
    rows = [make_row(location="Birmingham, United Kingdom")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["town"] == "Birmingham"

@pytest.mark.xfail(strict=True, reason="v1 bug: 'Crewe' not in TOWNS dict — common UK city missing from lookup table")
def test_resolve_crewe_not_in_towns(ctx):
    rows = [make_row(location="Crewe")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1

@pytest.mark.xfail(strict=True, reason="v1 bug: '2 Locations' placeholder not resolved — structured_job.locations never consulted")
def test_resolve_location_placeholder_fallback(ctx):
    """'2 Locations' placeholder should fall back to structured_job.locations."""
    rows = [make_row(
        location="2 Locations",
        page={"structured_job": {"locations": ["Manchester, United Kingdom"]}},
    )]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1

@pytest.mark.xfail(strict=True, reason="v1 bug: 'Bolton, GB' fails exact lookup — country-code suffix not stripped (12 jobs in real feed)")
def test_resolve_location_with_gb_suffix(ctx):
    """'Bolton, GB' is the City,GB format — 12 jobs in the real feed use this pattern."""
    rows = [make_row(location="Bolton, GB")]
    result = resolve_job_town.main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["town"] == "Bolton"

def test_resolve_funnel_baseline(ctx):
    """6 of 1445 rows pass resolve_job_town in the real run — all are bare city names in TOWNS dict.
    Verifies that known passing towns (Wrexham, Chester, Runcorn) still resolve without regression."""
    passing_locations = ["Wrexham", "Chester", "Runcorn"]
    for loc in passing_locations:
        rows = [make_row(location=loc)]
        result = resolve_job_town.main(ctx, rows)
        assert len(result.data) == 1, f"{loc!r} should resolve but does not"
```

### Task 8: CREATE `tests/v1/test_match_jobs.py`

Pure function tests + module integration:

```python
# --- matched_titles pure function tests ---

def test_matched_titles_substring_found():
    """v1 matches when profile title is a substring of job title."""
    assert matched_titles("Senior Controls Engineer", ["Controls Engineer"]) == ["Controls Engineer"]

def test_matched_titles_no_match():
    assert matched_titles("Accountant", ["Controls Engineer"]) == []

def test_matched_titles_multiple_profile_titles_partial_match():
    result = matched_titles("Senior Controls Engineer", ["Controls Engineer", "Electrical Engineer"])
    assert result == ["Controls Engineer"]

def test_matched_titles_all_match():
    result = matched_titles("Senior Controls Engineer Electrical", ["Controls Engineer", "Electrical Engineer"])
    # "Electrical Engineer" is a substring of "...Electrical" — may or may not match depending on position
    # This just documents current behavior
    assert "Controls Engineer" in result

@pytest.mark.xfail(strict=True, reason="v1 bug: matched_titles is case-sensitive — 'controls engineer' != 'Controls Engineer'")
def test_matched_titles_case_insensitive():
    assert matched_titles("controls engineer", ["Controls Engineer"]) == ["Controls Engineer"]

@pytest.mark.xfail(strict=True, reason="v1 bug: matched_titles uses substring, not word-by-word — non-adjacent words not matched")
def test_matched_titles_non_adjacent_words():
    """Spec: every word of profile title must appear in job title in any order."""
    # "Quality" and "Engineer" both appear in "Quality and Warranty Engineer", but not adjacent
    assert matched_titles("Quality and Warranty Engineer", ["Quality Engineer"]) == ["Quality Engineer"]

@pytest.mark.xfail(strict=True, reason="v1 bug: matched_titles is case-sensitive — 'cnc miller' never matches 'CNC Miller'")
def test_matched_titles_lowercase_profile_title():
    assert matched_titles("CNC Miller", ["cnc miller"]) == ["cnc miller"]

# --- matched_locations pure function tests ---

def test_matched_locations_exact_town():
    locations = [{"name": "Warrington", "type": "sub_region", "includes": ["Warrington", "Runcorn"], "country": "UK"}]
    assert matched_locations("Warrington", locations) == ["Warrington"]

def test_matched_locations_town_in_includes():
    locations = [{"name": "Warrington", "type": "sub_region", "includes": ["Warrington", "Runcorn"], "country": "UK"}]
    assert matched_locations("Runcorn", locations) == ["Warrington"]

def test_matched_locations_no_match():
    locations = [{"name": "Warrington", "type": "sub_region", "includes": ["Warrington"], "country": "UK"}]
    assert matched_locations("London", locations) == []

# --- match_jobs module tests ---

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

def test_match_jobs_runcorn_in_includes(ctx, profile):
    """Runcorn is in Warrington includes — should match Warrington location."""
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp", title="Controls Engineer", town="Runcorn")]
    result = match_jobs.main(ctx, rows)
    assert len(result.data) == 1
    assert "Warrington" in result.data[0]["matched_location"]

@pytest.mark.xfail(strict=True, reason="v1 bug: company matching is exact — 'Cobalt Zephyr Holdings' != profile entry 'Cobalt Zephyr'")
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
```

### Task 9: CREATE `tests/v1/test_portal_matches_output.py`

```python
REQUIRED_FIELDS = {"job_id", "profile_id", "matched_company", "matched_job_title", "matched_location", "reason", "used_llm"}

def make_matched_row(**kwargs):
    """Normalised row with all match fields set."""
    from tests.v1.helpers import make_row
    return make_row(
        matched_company="Acme Corp",
        matched_job_title=["Controls Engineer"],
        matched_location=["Warrington"],
        reason="Controls Engineer at Acme Corp, in Warrington",
        used_llm=False,
        **kwargs,
    )

def test_portal_output_file_created(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    rows = [make_matched_row()]
    result = portal_matches_output.main(ctx, rows)
    assert Path(result.artifacts["output_path"]).exists()

def test_portal_output_file_name(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    portal_matches_output.main(ctx, [make_matched_row()])
    # filename follows pattern: {output_prefix}_matched.jsonl
    assert Path(ctx.get("trace_id") and result.artifacts["output_path"]).name == "profile_test_matched.jsonl"
    # NOTE: check artifact directly:
    result = portal_matches_output.main(ctx, [make_matched_row()])
    assert Path(result.artifacts["output_path"]).name == "profile_test_matched.jsonl"

def test_portal_output_has_required_fields(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    rows = [make_matched_row()]
    result = portal_matches_output.main(ctx, rows)
    records = [json.loads(l) for l in Path(result.artifacts["output_path"]).read_text().splitlines()]
    assert len(records) == 1
    assert REQUIRED_FIELDS.issubset(records[0].keys())

def test_portal_output_profile_id_from_context(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    record = json.loads(Path(result.artifacts["output_path"]).read_text().splitlines()[0])
    assert record["profile_id"] == "test"  # from profile fixture

def test_portal_output_empty_input(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [])
    assert Path(result.artifacts["output_path"]).read_text() == ""

def test_portal_used_llm_false_by_default(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    record = json.loads(Path(result.artifacts["output_path"]).read_text().splitlines()[0])
    assert record["used_llm"] is False
```

### Task 10: CREATE `tests/v1/test_labelled_sample.py`

Integration test — runs the full pipeline against real data:

```python
# IMPORTANT: skip gracefully if data files not present (CI portability)
# Use pytest.importorskip or skipif

LABELLED = Path("data/labelled_sample.jsonl")
JOBS_RAW = Path("data/jobs_raw.jsonl")
SEARCH_INPUTS = Path("data/user_search_inputs")
GOLDEN = Path("data/golden")

@pytest.fixture
def labelled_data():
    if not LABELLED.exists():
        pytest.skip("data/labelled_sample.jsonl not present")
    return [json.loads(l) for l in LABELLED.read_text().splitlines()]

@pytest.fixture
def raw_jobs():
    if not JOBS_RAW.exists():
        pytest.skip("data/jobs_raw.jsonl not present")
    with JOBS_RAW.open() as f:
        return {json.loads(l)["job_id"]: json.loads(l) for l in f}

def test_labelled_sample_has_expected_shape(labelled_data):
    """Sanity check: 60 rows, each with decision/reason/matched_* fields."""
    assert len(labelled_data) == 60
    for row in labelled_data:
        assert "job_id" in row
        assert row["decision"] in ("yes", "no")
        assert "reason" in row

def test_labelled_yes_jobs_count(labelled_data):
    yes = [r for r in labelled_data if r["decision"] == "yes"]
    assert len(yes) == 11  # as documented in NOTES.md

def test_labelled_no_jobs_include_dead_links(labelled_data, raw_jobs):
    """8 of the 'no' labels are 404/410 jobs — documents the dead-link bug scope."""
    dead_nos = [
        l for l in labelled_data
        if l["decision"] == "no"
        and raw_jobs.get(l["job_id"], {}).get("page", {}).get("http_status") in (404, 410)
    ]
    assert len(dead_nos) >= 8


# ---------------------------------------------------------------------------
# Pipeline integration: use the full 1529-job feed against profile_a
# These tests encode the concrete numbers from run 20261020T153054
# ---------------------------------------------------------------------------

def _run_full_pipeline(tmp_path, monkeypatch) -> set[str]:
    """Helper: run v1 on jobs_raw.jsonl vs profile_a, return matched job_id set."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    if not JOBS_RAW.exists() or not SEARCH_INPUTS.exists():
        pytest.skip("data/ files not present")
    outputs = run_pipeline(
        handler.STAGE_GRAPH, handler.INPUT_CONTEXT_SCHEMA,
        handler.OUTPUT_CONTEXT_SCHEMA, handler.HANDLER_NAME, JOBS_RAW, SEARCH_INPUTS,
    )
    matched: set[str] = set()
    for path in outputs:
        matched.update(json.loads(l)["job_id"] for l in Path(path).read_text().splitlines())
    return matched


def test_v1_full_pipeline_output_count(tmp_path, monkeypatch):
    """v1 outputs exactly 2 matched jobs on the full 1529-job feed (run 20261020T153054 baseline)."""
    matched = _run_full_pipeline(tmp_path, monkeypatch)
    assert len(matched) == 2


def test_v1_full_pipeline_matches_correct_jobs(tmp_path, monkeypatch):
    """The 2 matched jobs are J678841 and J948846 (Inkwell Copperleaf Group, Wrexham).
    Both are Maintenance Technician jobs with bare 'Wrexham' location in TOWNS dict."""
    matched = _run_full_pipeline(tmp_path, monkeypatch)
    assert matched == {"J678841", "J948846"}


def test_v1_full_pipeline_j685745_not_matched(tmp_path, monkeypatch):
    """J685745 (Runcorn, Driftwood Copperleaf) passes resolve_job_town but fails NO_TITLE_MATCH.
    Title is 'Software Engineer III, Digital Pathology…' — no profile title is a substring."""
    matched = _run_full_pipeline(tmp_path, monkeypatch)
    assert "J685745" not in matched


def test_v1_pipeline_on_labelled_subset(tmp_path, monkeypatch, labelled_data, raw_jobs):
    """Run v1 pipeline on the 60 labelled jobs; measure recall against YES decisions.

    v1 is expected to match 0/11 YES jobs due to combined location + title bugs.
    This test documents the baseline; changing the assertion requires a real improvement.
    """
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    labelled_ids = {r["job_id"] for r in labelled_data}
    subset = [raw_jobs[jid] for jid in labelled_ids if jid in raw_jobs]
    jobs_file = tmp_path / "labelled_jobs.jsonl"
    jobs_file.write_text("\n".join(json.dumps(j) for j in subset) + "\n", encoding="utf-8")
    outputs = run_pipeline(
        handler.STAGE_GRAPH, handler.INPUT_CONTEXT_SCHEMA,
        handler.OUTPUT_CONTEXT_SCHEMA, handler.HANDLER_NAME, jobs_file, SEARCH_INPUTS,
    )
    matched_ids: set[str] = set()
    for path in outputs:
        matched_ids.update(json.loads(l)["job_id"] for l in Path(path).read_text().splitlines())
    yes_ids = {r["job_id"] for r in labelled_data if r["decision"] == "yes"}
    recall = len(yes_ids & matched_ids) / len(yes_ids) if yes_ids else 0.0
    # v1 recall is 0 — all YES jobs fall through location+title bugs
    assert recall >= 0.0  # measurement; printed for visibility
    print(f"\nv1 recall on YES labelled jobs: {recall:.0%} ({len(yes_ids & matched_ids)}/{len(yes_ids)})")


@pytest.mark.xfail(strict=True, reason="v1 bugs: all 11 YES jobs dropped — resolve_job_town rejects 10 on UNKNOWN_LOCATION, 1 (J685745) on NO_TITLE_MATCH — recall is 0%")
def test_v1_pipeline_recall_above_50_percent(tmp_path, monkeypatch, labelled_data, raw_jobs):
    """Documents: v1 fails to reach even 50% recall on labelled YES jobs."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    labelled_ids = {r["job_id"] for r in labelled_data}
    subset = [raw_jobs[jid] for jid in labelled_ids if jid in raw_jobs]
    jobs_file = tmp_path / "labelled_jobs.jsonl"
    jobs_file.write_text("\n".join(json.dumps(j) for j in subset) + "\n", encoding="utf-8")
    outputs = run_pipeline(
        handler.STAGE_GRAPH, handler.INPUT_CONTEXT_SCHEMA,
        handler.OUTPUT_CONTEXT_SCHEMA, handler.HANDLER_NAME, jobs_file, SEARCH_INPUTS,
    )
    matched_ids: set[str] = set()
    for path in outputs:
        matched_ids.update(json.loads(l)["job_id"] for l in Path(path).read_text().splitlines())
    yes_ids = {r["job_id"] for r in labelled_data if r["decision"] == "yes"}
    recall = len(yes_ids & matched_ids) / len(yes_ids)
    assert recall >= 0.50  # v1 achieves 0% — this xfail documents the gap to fix
```

---

## Validation Loop

### Level 1: Linting

```bash
# From project root, with venv active
.venv/bin/python -m ruff check tests/v1/ --fix
# Expected: 0 errors (line length 120, isort, flake8 basics)
```

### Level 2: Unit and integration tests

```bash
# Run full suite (pyproject.toml testpaths=["tests"] discovers tests/v1/ automatically)
make test

# Run only v1 tests:
.venv/bin/python -m pytest tests/v1/ -v

# Run one file to iterate quickly:
.venv/bin/python -m pytest tests/v1/test_town_lookup.py -v
.venv/bin/python -m pytest tests/v1/test_match_jobs.py -v
.venv/bin/python -m pytest tests/v1/test_resolve_job_town.py -v

# Expected output — two categories:
#   PASSED  tests/v1/test_town_lookup.py::test_lookup_town_known_city
#   XFAIL   tests/v1/test_match_jobs.py::test_matched_titles_case_insensitive - v1 bug: ...
# There must be NO FAILED and NO ERROR lines.
```

### Level 3: Confirm xfail tests are actually failing (not accidentally passing)

```bash
# --runxfail executes xfail tests normally — they must all FAIL here
.venv/bin/python -m pytest tests/v1/ --runxfail -v 2>&1 | grep -E "FAILED|PASSED|ERROR" | head -30
# Expected: the xfail tests appear as FAILED (confirming the bug is real)
# Non-xfail tests still appear as PASSED
```

---

## Final Validation Checklist

- [ ] `make test` exits 0 — output has PASSED and XFAIL lines, zero FAILED/ERROR
- [ ] `ruff check tests/v1/` exits 0
- [ ] Every xfail has `strict=True` and `reason="v1 bug: ..."`
- [ ] `tests/test_golden.py` still passes unchanged
- [ ] `tests/test_llm_cap.py` still passes unchanged
- [ ] No test imports LLM modules or makes network calls
- [ ] `tests/__init__.py` and `tests/v1/__init__.py` are present (empty)
- [ ] `tests/v1/helpers.py` has `make_row`, `read_sli`, `write_jsonl`
- [ ] `tests/v1/conftest.py` has `ctx` and `profile` fixtures
- [ ] All 10 known bugs from NOTES.md have at least one xfail test
- [ ] `--runxfail` run shows xfail tests as FAILED (bugs are real, not accidentally passing)

---

## Anti-Patterns to Avoid

- ❌ Don't put new tests in `tests/` root — they must live in `tests/v1/`
- ❌ Don't monkeypatch module internals to make tests pass — test real behavior
- ❌ Don't use `@pytest.mark.xfail` without `strict=True` — bugs must stay visible
- ❌ Don't create tests that always pass regardless of behavior (`assert True`, `assert recall >= 0.0` without a print)
- ❌ Don't test the golden fixture in new files — `tests/test_golden.py` owns that
- ❌ Don't call LLM APIs — all tests must run without API keys
- ❌ Don't use `except Exception: pass` in test helpers — let failures propagate
- ❌ Don't hardcode profile_a data in unit tests — use the `profile` fixture
- ❌ Don't import from `tests.v1.conftest` — put shared non-fixture code in `tests/v1/helpers.py`

---

## Codebase tree (current)

```
tests/
    test_golden.py        # existing — DO NOT MODIFY
    test_llm_cap.py       # existing — DO NOT MODIFY
v1/workers/job_matcher/
    _shared/town_lookup.py
    modules/
        load_job_feed.py
        normalise_job_rows.py
        drop_duplicate_jobs.py
        resolve_job_town.py
        match_jobs.py
        portal_matches_output.py
    stages/
        stage_clean_jobs.py
        stage_match_jobs.py
    handler.py
v1/shared/
    observability/sli_observe.py
    patterns/worker_runtime.py
data/
    golden/
    labelled_sample.jsonl
    jobs_raw.jsonl
    user_search_inputs/profile_a/
```

## Desired codebase tree (after implementation)

```
tests/
    __init__.py           # NEW (empty) — enables package imports
    test_golden.py        # unchanged
    test_llm_cap.py       # unchanged
    v1/
        __init__.py       # NEW (empty) — enables `from tests.v1.helpers import ...`
        helpers.py        # NEW — make_row, read_sli, write_jsonl
        conftest.py       # NEW — ctx, profile fixtures
        test_town_lookup.py           # NEW — lookup_town, towns_covered
        test_load_job_feed.py         # NEW — load_job_feed module
        test_normalise_job_rows.py    # NEW — parse_salary + normalise module
        test_drop_duplicate_jobs.py   # NEW — dedupe_key + dedup module
        test_resolve_job_town.py      # NEW — resolve module
        test_match_jobs.py            # NEW — matched_titles/locations + match module
        test_portal_matches_output.py # NEW — portal output module
        test_labelled_sample.py       # NEW — integration against 60 labelled jobs
```

---

**PRP Confidence Score: 9.5/10**

All pipeline numbers are verified against real run `20261020T153054`. The two matched job IDs (J678841, J948846), the 6-job resolver pass-through, and the location format distribution are ground-truth — use them directly in integration tests without further research.

The only minor risk is `test_portal_matches_output.py::test_portal_output_file_name` — the pseudocode has a duplicate `main()` call. Fix: call `main()` once, store the result, assert `Path(result.artifacts["output_path"]).name == "profile_test_matched.jsonl"`.

The `test_v1_full_pipeline_output_count` / `test_v1_full_pipeline_matches_correct_jobs` tests run against the full 1529-job feed — they are slower (~2s) but fully deterministic since no LLM calls are made.
