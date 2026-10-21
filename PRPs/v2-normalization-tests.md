# PRP: v2 Normalization Test Suite (Unit + Golden Dataset Integration)

## Goal

Implement a comprehensive test suite for the 5 normalization modules in `v2/workers/job_matcher/normalization/`. Tests live in `tests/v2/` and use the 300-job golden dataset (`tests/v2/golden-dataset/`) as the ground truth source for integration tests.

**End state**: Two test files are complete and all tests pass with `make test`.

1. `tests/v2/test_normalization.py` — extended with filter_duplicates unit tests, SLI event assertion tests, and additional edge cases for all modules
2. `tests/v2/test_normalization_golden.py` — new golden dataset integration tests that verify normalization precision on YES jobs and catch dead link filtering

---

## Why

- `filter_duplicates` has zero test coverage despite being a critical pipeline module
- SLI event assertions are missing across all modules — the observability contract (which rejection reason is written) is untested
- The golden dataset (300 hand-labelled jobs, 18 YES / 282 NO) exists but is only used in `test_labelled_sample.py` (which requires a live LLM key). Normalization tests should run without any LLM key.
- Integration tests against real data catch bugs that unit tests with toy fixtures miss (e.g., location edge cases from structured_job arrays)

---

## What

### Modules under test (all in `v2/workers/job_matcher/normalization/`)

| Module | Type | Rejection reasons |
|--------|------|-------------------|
| `filter_dead_links.py` | filter | `DEAD_LINK`, `BLOCKED_PAGE` |
| `filter_duplicates.py` | filter | `DUPLICATE` |
| `resolve_location.py` | filter | `LOCATION_NOT_IN_PROFILE` |
| `resolve_title.py` | filter | `TITLE_NOT_IN_PROFILE` |
| `resolve_company.py` | filter | `COMPANY_NOT_IN_PROFILE` |

### Success Criteria

- [ ] `filter_duplicates` has ≥ 5 unit tests (unique ids, duplicate rejection, first-kept, empty input, SLI)
- [ ] Every rejection reason is covered by at least one SLI assertion test
- [ ] `tests/v2/test_normalization_golden.py` has tests that pass without LLM API key
- [ ] All 18 YES jobs pass the full normalization pipeline without rejection
- [ ] All 29 dead-link-labelled jobs are rejected by `filter_dead_links`
- [ ] `make test` is green with no regressions

---

## All Needed Context

### Files to read before implementing

```yaml
# SOURCE MODULES — read all five before writing tests
- file: v2/workers/job_matcher/normalization/filter_dead_links.py
  why: Understand dead status codes (_DEAD_STATUSES = {404, 410}, _BLOCKED_STATUSES = {403, 405}),
       the empty-content check (no title + no h1 + no company → BLOCKED_PAGE)

- file: v2/workers/job_matcher/normalization/filter_duplicates.py
  why: Deduplication is by job_id (not title|company like v1). First occurrence kept.

- file: v2/workers/job_matcher/normalization/resolve_location.py
  why: Reads location strings from sj.locations[], sj.location, sj.additional_locations[], scraped.location.
       Skips "N Locations" placeholders. Sets row["location_strings"] and row["is_remote_hint"].
       Rejects if no city token matches AND job is not remote (or profile has no remote location).

- file: v2/workers/job_matcher/normalization/resolve_title.py
  why: Resolves title from structured_job > title_tag (split on |/-) > h1 > scraped.title.
       Sets row["resolved_title"]. Deduplicates words into frozenset, strips trailing 's' on
       words longer than 3 chars. Rejects if no overlap with profile title words.

- file: v2/workers/job_matcher/normalization/resolve_company.py
  why: Resolves from structured_job.company > scraped.company. Tokenises: removes legal suffixes
       (Ltd, plc, Group, Holdings, etc.), punctuation, and short words. Rejects if no token overlap.

# TEST INFRASTRUCTURE — understand before writing
- file: tests/v2/conftest.py
  why: Has ctx fixture (trace_id="t", ILLUMINI_RUNS_DIR → tmp_path), profile fixture (small test
       profile), and make_row() function. make_row is NOT a fixture — import it directly:
       `from tests.v2.conftest import make_row`

- file: tests/v1/helpers.py
  why: Has read_sli(tmp_path, trace_id="t") pattern to copy into tests/v2/conftest.py

- file: tests/v1/test_drop_duplicate_jobs.py
  why: Reference for filter_duplicates test structure and SLI assertion pattern

- file: tests/v1/test_resolve_job_town.py
  why: Reference for location test structure, parametrize patterns, xfail patterns

- file: tests/v2/test_normalization.py
  why: Existing tests to extend (do NOT duplicate — add below the last test in each section)

# GOLDEN DATASET — read the structure
- file: tests/v2/golden-dataset/labelled_300.jsonl
  why: 300 labels. Schema: {job_id, decision, reason, matched_company, matched_job_title, matched_location}
       decision: "yes" (18 rows) | "no" (282 rows)
       NO reason categories: "404/410 dead" (29), "location" (14), "title" (100), "company" (58), "other" (81)

- file: tests/v2/golden-dataset/jobs.jsonl
  why: 300 raw job rows. Schema: {job_id, scraped: {title, company, location, salary}, source_url, page}
       page has: {http_status, title_tag?, h1?, meta?, text?, structured_job?}

- file: tests/v2/golden-dataset/user_search_inputs/profile_a/company_searches.json
- file: tests/v2/golden-dataset/user_search_inputs/profile_a/job_title_searches.json
- file: tests/v2/golden-dataset/user_search_inputs/profile_a/location_searches.json
  why: Real profile_a with 200+ companies, 57 titles, 12 locations. Load with load_search_inputs().

# SHARED INFRASTRUCTURE
- file: v2/shared/observability/sli_observe.py
  why: META_OUTCOME="META_OUTCOME", META_REJECTION_REASON="META_REJECTION_REASON".
       sli_observe() writes to runs/<trace_id>/sli_events.jsonl (redirected by ILLUMINI_RUNS_DIR env var)

- file: v2/shared/patterns/worker_runtime.py
  why: load_search_inputs(root: Path) -> list[tuple[str, dict]] — loads profile_a from folder.
       Returns [(folder_name, profile_dict)] where profile_dict has keys: profile_id, companies, titles, locations.
```

### Codebase tree (relevant section)

```
tests/
  v2/
    __init__.py
    conftest.py                  ← MODIFY: add read_sli() helper
    golden-dataset/
      jobs.jsonl                 (300 raw jobs)
      labelled_300.jsonl         (300 labels: decision + reason)
      user_search_inputs/
        profile_a/
          company_searches.json
          job_title_searches.json
          location_searches.json
    test_normalization.py        ← MODIFY: add filter_duplicates + SLI + edge case tests
    test_normalization_golden.py ← CREATE: golden dataset integration tests

v2/workers/job_matcher/normalization/
  filter_dead_links.py
  filter_duplicates.py
  resolve_location.py
  resolve_title.py
  resolve_company.py
```

### Known gotchas

```python
# CRITICAL: make_row is NOT a pytest fixture — import it directly
from tests.v2.conftest import make_row  # ✓ correct
# def test_foo(make_row):  # ✗ wrong — pytest will try to find a fixture named make_row

# CRITICAL: SLI files go to tmp_path/<trace_id>/sli_events.jsonl
# ctx fixture sets trace_id="t", so SLI is at: tmp_path / "t" / "sli_events.jsonl"
# Tests that read SLI must receive tmp_path as a parameter AND set ILLUMINI_RUNS_DIR
# The ctx fixture already does monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))

# CRITICAL: The profile fixture in conftest.py has:
#   companies: [{"name": "Acme Corp"}, {"name": "Siemens Energy"}]  
#   titles: ["Controls Engineer", "Electrical Engineer", "Quality Engineer"]
#   locations: [Warrington sub_region (includes Warrington, Runcorn, Knutsford), Remote UK]
# Profile must be set on context: ctx["profile"] = profile  (before calling module.main)

# CRITICAL: All rows need META_OUTCOME = "pass" initially — make_row() sets this.
# When doing deep copies for golden dataset tests, reset: row[META_OUTCOME] = "pass"

# CRITICAL: resolve_location requires context["profile"]["locations"] — the profile fixture has this.
# resolve_title requires context["profile"]["titles"].
# resolve_company requires context["profile"]["companies"].
# filter_dead_links and filter_duplicates do NOT read from context["profile"].

# GOTCHA: filter_dead_links rejects rows where:
#   1. http_status in {404, 410}  → reason: "DEAD_LINK"
#   2. http_status in {403, 405}  → reason: "BLOCKED_PAGE"
#   3. status 200 but no sj.title AND no h1.strip() AND no sj.company → "BLOCKED_PAGE"
# A 200 row with EITHER a structured_job.title OR a non-empty h1 → passes.

# GOTCHA: resolve_title strips trailing 's' on words > 3 chars:
#   "Engineers" → "engineer" → matches profile title "Controls Engineer" (has "engineer")
#   But "is" (2 chars) stays as "is", "has" (3 chars) stays as "has"

# GOTCHA: resolve_company legal suffix list is LONG — includes "ltd", "plc", "group",
#   "holdings", "international", "uk", "engineering", "services", "solutions", etc.
#   "Siemens Energy Ltd" → after stripping "ltd" → tokens {"siemens", "energy"} → matches

# GOTCHA: resolve_location sets row["location_strings"] and row["is_remote_hint"] on EVERY row
#   (even rejected ones). resolved_title and resolved_company are only set on kept rows... 
#   Actually: all rows get resolved_title / resolved_company set (the reject happens after setting).

# GOTCHA: load_search_inputs returns [(folder_name, profile)] where folder_name is "profile_a"
#   Result: dict(load_search_inputs(SEARCH_INPUTS)) gives {"profile_a": {...profile dict...}}
#   The profile dict has structure: {"profile_id": "a", "companies": [...], "titles": [...], "locations": [...]}

# GOTCHA: scope="module" fixtures (golden_data, profile_a) cannot request function-scoped
#   fixtures (tmp_path, monkeypatch). Keep golden_ctx as function-scoped; request profile_a
#   (module-scoped) + tmp_path + monkeypatch normally.
```

---

## Implementation Blueprint

### Task 1: Add `read_sli` helper to `tests/v2/conftest.py`

```python
# ADD at the bottom of tests/v2/conftest.py

import json
from pathlib import Path

def read_sli(tmp_path: Path, trace_id: str = "t") -> list[dict]:
    """Read SLI events written during a module call (mirrors tests/v1/helpers.py)."""
    path = tmp_path / trace_id / "sli_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

### Task 2: Add `filter_duplicates` section to `tests/v2/test_normalization.py`

Add the following section BEFORE the existing `# ── resolve_company` section (or at the end — keep it together):

```python
# ── filter_duplicates ────────────────────────────────────────────────────────

def test_filter_duplicates_unique_ids_all_kept(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main
    rows = [make_row(job_id="J001"), make_row(job_id="J002", title="Electrical Engineer")]
    result = main(ctx, rows)
    assert len(result.data) == 2


def test_filter_duplicates_same_id_first_kept(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main
    rows = [make_row(job_id="J001"), make_row(job_id="J001", title="Electrical Engineer")]
    result = main(ctx, rows)
    assert len(result.data) == 1
    assert result.data[0]["title"] == "Controls Engineer"  # default from make_row — first kept


def test_filter_duplicates_three_same_only_first_kept(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main
    rows = [make_row(job_id="J001"), make_row(job_id="J001"), make_row(job_id="J001")]
    result = main(ctx, rows)
    assert len(result.data) == 1


def test_filter_duplicates_empty_input(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main
    result = main(ctx, [])
    assert result.data == []


def test_filter_duplicates_sli_marks_duplicate(ctx, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.filter_duplicates import main
    rows = [make_row(job_id="J001"), make_row(job_id="J001")]
    main(ctx, rows)
    sli = read_sli(tmp_path)
    dupes = [e for e in sli if e.get(META_REJECTION_REASON) == "DUPLICATE"]
    assert len(dupes) == 1


def test_filter_duplicates_mixed_batch_keeps_unique_rejects_dupe(ctx):
    from v2.workers.job_matcher.normalization.filter_duplicates import main
    rows = [
        make_row(job_id="J001"),
        make_row(job_id="J002", title="Electrical Engineer"),
        make_row(job_id="J001", title="Quality Engineer"),  # duplicate of J001
    ]
    result = main(ctx, rows)
    assert len(result.data) == 2
    kept_ids = {r["job_id"] for r in result.data}
    assert kept_ids == {"J001", "J002"}
```

### Task 3: Add SLI assertion tests to `tests/v2/test_normalization.py`

Add a new `# ── SLI event assertions ──` section after the existing tests:

```python
# ── SLI event assertions ─────────────────────────────────────────────────────

def test_filter_dead_links_sli_dead_link_reason(ctx, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    row = make_row()
    row["page"] = {"http_status": 404}
    main(ctx, [row])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "DEAD_LINK" for e in sli)


def test_filter_dead_links_sli_blocked_page_reason(ctx, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    row = make_row()
    row["page"] = {"http_status": 403}
    main(ctx, [row])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "BLOCKED_PAGE" for e in sli)


def test_resolve_location_sli_not_in_profile_reason(ctx, profile, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.resolve_location import main
    ctx["profile"] = profile
    main(ctx, [make_row(location="Edinburgh, Scotland")])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "LOCATION_NOT_IN_PROFILE" for e in sli)


def test_resolve_title_sli_not_in_profile_reason(ctx, profile, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.resolve_title import main
    ctx["profile"] = profile
    main(ctx, [make_row(title="Marketing Director")])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "TITLE_NOT_IN_PROFILE" for e in sli)


def test_resolve_company_sli_not_in_profile_reason(ctx, profile, tmp_path):
    from tests.v2.conftest import read_sli
    from v2.shared.observability.sli_observe import META_REJECTION_REASON
    from v2.workers.job_matcher.normalization.resolve_company import main
    ctx["profile"] = profile
    main(ctx, [make_row(company="Unknown Corp XYZ")])
    sli = read_sli(tmp_path)
    assert any(e.get(META_REJECTION_REASON) == "COMPANY_NOT_IN_PROFILE" for e in sli)
```

### Task 4: Add edge case tests to `tests/v2/test_normalization.py`

```python
# ── filter_dead_links (additional) ───────────────────────────────────────────

def test_filter_dead_links_410_rejected(ctx):
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    row = make_row()
    row["page"] = {"http_status": 410}
    assert len(main(ctx, [row]).data) == 0


def test_filter_dead_links_405_blocked(ctx):
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    row = make_row()
    row["page"] = {"http_status": 405}
    assert len(main(ctx, [row]).data) == 0


def test_filter_dead_links_200_no_content_rejected(ctx):
    """200 page with no structured_job, no h1, no company — unverifiable → BLOCKED_PAGE."""
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    row = make_row()
    row["page"] = {"http_status": 200, "h1": None, "structured_job": {}}
    assert len(main(ctx, [row]).data) == 0


def test_filter_dead_links_200_h1_only_passes(ctx):
    """200 page with h1 but no structured_job — verifiable via h1."""
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    row = make_row()
    row["page"] = {"http_status": 200, "h1": "Controls Engineer", "structured_job": {}}
    assert len(main(ctx, [row]).data) == 1


# ── resolve_title (additional) ────────────────────────────────────────────────

def test_resolve_title_h1_fallback_matches_profile(ctx, profile):
    """h1 is used when no structured_job.title and no title_tag."""
    from v2.workers.job_matcher.normalization.resolve_title import main
    ctx["profile"] = profile
    row = make_row(title="Wrong scraped")
    row["page"] = {"http_status": 200, "h1": "Electrical Engineer", "structured_job": {}}
    result = main(ctx, [row])
    assert len(result.data) == 1
    assert result.data[0]["resolved_title"] == "Electrical Engineer"


def test_resolve_title_plural_word_matches(ctx, profile):
    """'Controls Engineers' (trailing s stripped) still matches 'Controls Engineer'."""
    from v2.workers.job_matcher.normalization.resolve_title import main
    ctx["profile"] = profile
    result = main(ctx, [make_row(title="Controls Engineers")])
    assert len(result.data) == 1


def test_resolve_title_sets_resolved_title_field(ctx, profile):
    """resolved_title is set on the row whether kept or rejected."""
    from v2.workers.job_matcher.normalization.resolve_title import main
    ctx["profile"] = profile
    rows = [make_row(title="Controls Engineer")]
    main(ctx, rows)
    assert rows[0]["resolved_title"] == "Controls Engineer"


# ── resolve_company (additional) ──────────────────────────────────────────────

def test_resolve_company_legal_suffix_stripped(ctx, profile):
    """'Siemens Energy Ltd' matches profile 'Siemens Energy' (strips 'ltd')."""
    from v2.workers.job_matcher.normalization.resolve_company import main
    ctx["profile"] = profile
    result = main(ctx, [make_row(company="Siemens Energy Ltd")])
    assert len(result.data) == 1


def test_resolve_company_sets_resolved_company_field(ctx, profile):
    """resolved_company is always set, even on rejected rows."""
    from v2.workers.job_matcher.normalization.resolve_company import main
    ctx["profile"] = profile
    rows = [make_row(company="Acme Corp")]
    main(ctx, rows)
    assert rows[0]["resolved_company"] == "Acme Corp"


# ── resolve_location (additional) ─────────────────────────────────────────────

def test_resolve_location_sj_locations_array(ctx, profile):
    """Locations from structured_job.locations[] array are collected."""
    from v2.workers.job_matcher.normalization.resolve_location import main
    ctx["profile"] = profile
    row = make_row(location="2 Locations")
    row["page"] = {"http_status": 200, "structured_job": {"locations": ["Warrington, UK", "London"]}}
    result = main(ctx, [row])
    assert len(result.data) == 1  # Warrington is in profile


def test_resolve_location_sets_location_strings_field(ctx, profile):
    """location_strings is always set on every row after resolve_location."""
    from v2.workers.job_matcher.normalization.resolve_location import main
    ctx["profile"] = profile
    rows = [make_row(location="Warrington")]
    main(ctx, rows)
    assert "location_strings" in rows[0]
    assert rows[0]["is_remote_hint"] is False
```

### Task 5: Create `tests/v2/test_normalization_golden.py`

```python
"""Golden dataset integration tests for v2 normalization pipeline.

No LLM key required. Uses 300 hand-labelled jobs from tests/v2/golden-dataset/.
Profile: real profile_a (200+ companies, 57 titles, 12 locations across NW England).

Key assertions:
- All 18 YES jobs pass all 5 normalization stages (precision = 100% on YES)
- Jobs labelled with "404/410" dead-link reason are rejected by filter_dead_links
- After the full normalization pipeline, all 18 YES jobs remain
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from v2.shared.observability.sli_observe import META_OUTCOME

GOLDEN_DIR = Path("tests/v2/golden-dataset")
JOBS_PATH = GOLDEN_DIR / "jobs.jsonl"
LABELS_PATH = GOLDEN_DIR / "labelled_300.jsonl"
SEARCH_INPUTS = GOLDEN_DIR / "user_search_inputs"


# ── helpers ───────────────────────────────────────────────────────────────────

def _raw_to_row(raw: dict) -> dict:
    """Convert raw golden dataset job to v2 post-load_job_feed row shape."""
    scraped = raw.get("scraped") or {}
    return {
        "job_id": raw["job_id"],
        "title": scraped.get("title", "").strip(),
        "company": scraped.get("company", "").strip(),
        "location": scraped.get("location", "").strip(),
        "salary_gbp": None,
        "source_url": raw.get("source_url", ""),
        "page": raw.get("page") or {},
        META_OUTCOME: "pass",
    }


def _fresh_rows(rows: list[dict]) -> list[dict]:
    """Shallow-copy rows and reset META_OUTCOME='pass' for a clean test run."""
    out = [r.copy() for r in rows]
    for r in out:
        r[META_OUTCOME] = "pass"
    return out


# ── module-scoped fixtures (loaded once per test session) ─────────────────────

@pytest.fixture(scope="module")
def golden_rows():
    """All 300 golden dataset jobs in v2 row shape."""
    raws = [json.loads(l) for l in JOBS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [_raw_to_row(r) for r in raws]


@pytest.fixture(scope="module")
def labels():
    """Dict of {job_id: label_dict} for all 300 labelled jobs."""
    return {
        json.loads(l)["job_id"]: json.loads(l)
        for l in LABELS_PATH.read_text(encoding="utf-8").splitlines()
        if l.strip()
    }


@pytest.fixture(scope="module")
def profile_a():
    """Real profile_a loaded from golden dataset user_search_inputs/."""
    from v2.shared.patterns.worker_runtime import load_search_inputs
    return dict(load_search_inputs(SEARCH_INPUTS))["profile_a"]


# ── function-scoped context (tmp_path is function-scoped) ─────────────────────

@pytest.fixture
def gctx(tmp_path, monkeypatch, profile_a):
    """Context dict for golden dataset tests: profile_a + SLI → tmp_path."""
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    return {"trace_id": "golden", "profile": profile_a}


# ── derived id sets ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def yes_ids(labels):
    return frozenset(jid for jid, lbl in labels.items() if lbl["decision"] == "yes")


@pytest.fixture(scope="module")
def dead_link_ids(labels):
    """Jobs whose label reason mentions 404 or 410."""
    return frozenset(
        jid for jid, lbl in labels.items()
        if "404" in lbl.get("reason", "") or "410" in lbl.get("reason", "")
    )


# ── per-module precision tests (YES jobs must not be rejected) ────────────────

def test_filter_dead_links_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    yes_rows = [r for r in _fresh_rows(golden_rows) if r["job_id"] in yes_ids]
    result = main(gctx, yes_rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = yes_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected by filter_dead_links: {sorted(rejected)}"


def test_resolve_location_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    from v2.workers.job_matcher.normalization.resolve_location import main
    yes_rows = [r for r in _fresh_rows(golden_rows) if r["job_id"] in yes_ids]
    result = main(gctx, yes_rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = yes_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected by resolve_location: {sorted(rejected)}"


def test_resolve_title_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    from v2.workers.job_matcher.normalization.resolve_title import main
    yes_rows = [r for r in _fresh_rows(golden_rows) if r["job_id"] in yes_ids]
    result = main(gctx, yes_rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = yes_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected by resolve_title: {sorted(rejected)}"


def test_resolve_company_does_not_reject_yes_jobs(gctx, golden_rows, yes_ids):
    from v2.workers.job_matcher.normalization.resolve_company import main
    yes_rows = [r for r in _fresh_rows(golden_rows) if r["job_id"] in yes_ids]
    result = main(gctx, yes_rows)
    passed_ids = {r["job_id"] for r in result.data}
    rejected = yes_ids - passed_ids
    assert not rejected, f"YES jobs incorrectly rejected by resolve_company: {sorted(rejected)}"


# ── dead-link recall test ─────────────────────────────────────────────────────

def test_filter_dead_links_rejects_all_dead_link_labelled_jobs(gctx, golden_rows, dead_link_ids):
    """Every job labelled '404/410 dead' must be caught by filter_dead_links."""
    from v2.workers.job_matcher.normalization.filter_dead_links import main
    dead_rows = [r for r in _fresh_rows(golden_rows) if r["job_id"] in dead_link_ids]
    result = main(gctx, dead_rows)
    passed_ids = {r["job_id"] for r in result.data}
    still_passing = dead_link_ids & passed_ids
    assert not still_passing, f"Dead-link jobs not rejected: {sorted(still_passing)}"


# ── full pipeline precision test ──────────────────────────────────────────────

def test_full_normalization_preserves_all_yes_jobs(gctx, golden_rows, yes_ids):
    """Run all 5 normalization stages sequentially; all 18 YES jobs must survive."""
    from v2.workers.job_matcher.normalization import (
        filter_dead_links,
        filter_duplicates,
        resolve_location,
        resolve_title,
        resolve_company,
    )
    data = _fresh_rows(golden_rows)
    for module in [filter_dead_links, filter_duplicates, resolve_location, resolve_title, resolve_company]:
        data = module.main(gctx, data).data

    passed_ids = {r["job_id"] for r in data}
    missed = yes_ids - passed_ids
    assert not missed, (
        f"YES jobs lost in normalization pipeline: {sorted(missed)}\n"
        f"Normalization must not over-filter YES jobs — investigate which stage rejects them."
    )


def test_full_normalization_reduces_feed_significantly(gctx, golden_rows, yes_ids):
    """Normalization must filter at least some of the 300 jobs (not a no-op)."""
    from v2.workers.job_matcher.normalization import (
        filter_dead_links,
        filter_duplicates,
        resolve_location,
        resolve_title,
        resolve_company,
    )
    data = _fresh_rows(golden_rows)
    for module in [filter_dead_links, filter_duplicates, resolve_location, resolve_title, resolve_company]:
        data = module.main(gctx, data).data

    # Must reduce the feed AND keep at least all YES jobs
    assert len(data) < len(golden_rows), "Normalization must reject at least some jobs"
    assert len(data) >= len(yes_ids), f"Cannot reject more than {300 - len(yes_ids)} jobs without losing YES jobs"
```

---

## List of tasks (in order)

```yaml
Task 1 — Modify tests/v2/conftest.py:
  - ADD import json at the top (if not present)
  - ADD import Path from pathlib (if not present)
  - ADD read_sli(tmp_path, trace_id="t") standalone function at the bottom of the file
  - Pattern to follow: tests/v1/helpers.py read_sli function (identical logic)

Task 2 — Modify tests/v2/test_normalization.py:
  - ADD a new section "# ── filter_duplicates" with 6 unit tests
    (unique ids kept, same id first kept, three same only first, empty input, SLI marks duplicate, mixed batch)
  - ADD a new section "# ── SLI event assertions" with 5 tests
    (one per rejection reason: DEAD_LINK, BLOCKED_PAGE, LOCATION_NOT_IN_PROFILE, TITLE_NOT_IN_PROFILE, COMPANY_NOT_IN_PROFILE)
  - ADD additional edge case tests for filter_dead_links (410, 405, 200-no-content, 200-h1-only)
  - ADD edge case tests for resolve_title (h1 fallback, plural word, sets resolved_title)
  - ADD edge case tests for resolve_company (legal suffix stripped, sets resolved_company)
  - ADD edge case tests for resolve_location (sj.locations array, sets location_strings)

Task 3 — Create tests/v2/test_normalization_golden.py:
  - CREATE new file with golden dataset integration tests
  - Follow exact pseudocode structure from Implementation Blueprint above
  - 5 precision tests (one per module: "does not reject YES jobs")
  - 1 dead-link recall test
  - 1 full pipeline precision test
  - 1 full pipeline reduction sanity test

Task 4 — Run tests to verify:
  - .venv/bin/python -m pytest tests/v2/test_normalization.py -v
  - .venv/bin/python -m pytest tests/v2/test_normalization_golden.py -v
  - .venv/bin/python -m pytest tests/ -q (full suite — no regressions)
```

---

## Validation Loop

### Level 1: Static checks

```bash
# From project root — uses project's venv
.venv/bin/python -m ruff check tests/v2/test_normalization.py tests/v2/test_normalization_golden.py tests/v2/conftest.py
# Expected: no errors

.venv/bin/python -m ruff check --fix tests/v2/test_normalization.py tests/v2/test_normalization_golden.py tests/v2/conftest.py
```

### Level 2: New test files

```bash
# Unit tests — filter_duplicates and SLI additions
.venv/bin/python -m pytest tests/v2/test_normalization.py -v
# Expected: all pass, no LLM key needed

# Golden dataset integration tests
.venv/bin/python -m pytest tests/v2/test_normalization_golden.py -v
# Expected: all pass, no LLM key needed
# Note: if a YES job is unexpectedly rejected by normalization, the test message will tell you
# exactly which job and which stage rejected it — investigate the module logic.
```

### Level 3: Full suite (regression check)

```bash
make test
# OR
.venv/bin/python -m pytest tests/ -q
# Expected: existing tests still pass, new tests also pass
# test_labelled_sample.py is skipped if no API key — that's fine
```

---

## Anti-patterns to avoid

- Do NOT duplicate tests that already exist in `test_normalization.py` (filter_dead_links 404, 403, 200; resolve_company pass/reject/structured_job; resolve_title match/no-overlap/structured_job/title_tag; resolve_location city/includes/unknown/remote/placeholder/additional_locations)
- Do NOT add `xfail` marks — the normalization modules are correct v2 implementations (no known bugs)
- Do NOT mock `sli_observe` or write to SLI manually — let the module call it naturally
- Do NOT use `scope="module"` for `gctx` — it depends on function-scoped `tmp_path` and `monkeypatch`
- Do NOT pass `tmp_path` as an argument to module-scoped fixtures — they can't request function-scoped ones
- Do NOT import `make_row` as a fixture parameter — call it directly after `from tests.v2.conftest import make_row`

---

## Final validation checklist

- [ ] `read_sli` added to `tests/v2/conftest.py`
- [ ] `filter_duplicates` has ≥ 5 passing tests
- [ ] All 5 rejection reasons have a SLI assertion test
- [ ] `tests/v2/test_normalization_golden.py` exists with ≥ 8 tests
- [ ] All 18 YES jobs pass full normalization pipeline (or a normalization bug is found and reported)
- [ ] All 29 dead-link jobs are rejected by filter_dead_links
- [ ] `make test` is green

---

## PRP score: 9/10

High confidence for one-pass implementation. The only uncertainty is whether all 18 YES jobs in the golden dataset cleanly pass all 5 normalization stages without edge-case failures (e.g., if a YES job's location doesn't appear as a standalone city token in resolve_location). If a test fails, the error message is designed to name the specific job_id and module, making diagnosis fast.
