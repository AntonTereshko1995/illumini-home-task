# PRP: Improve match_jobs Jev Prompt Quality

## Goal

Fix six concrete defects in `v2/workers/job_matcher/agent/match_jobs.py` that
cause incorrect rejection reasons, wasted tokens, and avoidable model confusion.
Only this one file and a new test file change.

## Why

- **Wrong rejection reason logged**: for a US job (Warrington, PA) the recorded
  reason is `DEAD_LINK` (0.36 confidence) instead of `WRONG_COUNTRY`.  Root cause:
  `rejection_reason` is asked as a ChoiceQuestion in parallel with match questions.
  The model never sees whether company=0.99, title=0.98, locs≈0 — it only sees raw
  state and guesses.
- **Token waste on obvious non-matches**: all 57 profile titles are sent for every
  job, though at most 1–3 are plausible.  For "Controls Engineer", 56 of 57 title
  questions return 0.02–0.03 — pure waste.
- **300-line company list on every call**: the company NoulQuestion embeds the full
  list of ~300 companies.  `_find_matched_company()` (already in the file) can find
  the single best candidate before the call, reducing the company instruction from
  ~5 000 chars to ~100 chars.
- **No country signal in state**: when `location_strings` = `["Warrington, PA,
  United States"]`, loc questions for UK regions (Runcorn, Warrington UK) return
  0.03–0.07 instead of 0.0 because the model sees "Warrington" in both the state
  and the includes lists.  Explicitly adding `"location_country"` to the state
  gives the model an unambiguous signal.
- **`criteria` on NoulQuestion is pure noise**: every title and location NoulQuestion
  carries a `criteria={"true": "Job title matches ...", "false": "Job title does NOT
  match ..."}` field.  `criteria` is semantically meaningful only for `ChoiceQuestion`
  — for `NoulQuestion` only `instructions` matters.  Removing it saves ~40 tokens
  per question × 57 title questions = **~2 280 tokens per call** with zero effect on
  answer quality.
- **Duplicate `location_strings`**: the logged state shows `["Warrington, PA, United
  States", "Warrington, PA, United States"]` — the same string twice.  Jev
  processes both, the model sees the signal twice for no reason.  Deduplicate before
  building state.
- **`url` hint in company instruction is misleading**: the instruction says "Consider
  the company name in title_tag, url, and title" but the logged URL is
  `https://feed.example/jobs/s0001435` — a sanitized feed URL with no company name.
  Remove `url` from the company question instruction to avoid sending a false signal.

## What

Single file edit: `v2/workers/job_matcher/agent/match_jobs.py`
New test file:   `tests/v2/test_match_jobs.py`

### Concrete changes inside `match_jobs.py`

| Change | Before | After |
|--------|--------|-------|
| rejection_reason | ChoiceQuestion sent to jev | Removed; computed deterministically in Python |
| title questions | 57 NoulQuestion per call | Only titles sharing ≥1 word with resolved_title |
| company question | 300-company list in instructions | Pre-find candidate; ask jev to confirm only that one |
| state | missing country signal | Add `"location_country"` from `_detect_location_country()` |
| NoulQuestion criteria | redundant `criteria=` on every title/loc Noul | Removed; only `instructions` used |
| location_strings | may contain duplicates | Deduplicated before state is built |
| company instruction | "Consider title_tag, **url**, and title" | Remove `url` — sanitized feed URLs carry no company name |

### Success Criteria

- [ ] `rejection_reason` for Warrington PA job → `WRONG_COUNTRY`, not `DEAD_LINK`
- [ ] Title questions per call ≤ count of titles sharing words with job title
- [ ] Company instruction length < 200 chars (single company name, not full list)
- [ ] State includes `"location_country"` key
- [ ] No `criteria=` kwarg on any NoulQuestion (title_* or loc_*)
- [ ] `location_strings` in state are deduplicated
- [ ] `url` removed from company instruction text
- [ ] All existing tests pass: `pytest tests/ -q`
- [ ] New unit tests pass: `pytest tests/v2/test_match_jobs.py -v`

---

## All Needed Context

### Files to Read Before Coding

```yaml
- file: v2/workers/job_matcher/agent/match_jobs.py
  why: The only file being modified; know every function

- file: v2/shared/api_calls/llm.py
  why: decide_async() signature; NoulQuestion / ChoiceQuestion dataclasses

- file: v2/workers/job_matcher/normalization/resolve_company.py
  why: _tokenize() and _find_matched_company() are mirrors of the same logic here;
       by the time rows reach match_jobs, resolved_company already passed token-overlap
       check — so _find_matched_company will always return a candidate (or reject)

- file: v2/workers/job_matcher/normalization/resolve_title.py
  why: _title_words() does the same de-pluralising / splitting as what we need
       to pre-filter title questions

- file: v2/shared/observability/sli_observe.py
  why: passed() / reject() / sli_observe() contract

- file: tests/v2/conftest.py
  why: make_row() helper; ctx/profile fixtures; copy the pattern exactly

- file: tests/v2/normalizations/conftest.py
  why: fresh_rows(), golden fixtures (gctx, golden_rows, yes_ids)

- file: tests/v2/normalizations/test_normalise_location.py
  why: exact test file structure to mirror for test_match_jobs.py
```

### Real logged call to understand the problem

The JSON below is from `runs/20261023T185439/llm_prompts.jsonl` — a real failure case:

```
state: company="Aire Calder", title="Controls Engineer",
       location_strings=["Warrington, PA, United States", "Warrington, PA, United States"],
       ← BUG: same string twice; dedup before building state
       is_remote=false
answers:
  company = 0.99   ← passes
  title_10 = 0.98  ← "Controls Engineer" passes
  all title_* except title_10 ≈ 0.02
  loc_6 = 0.04 (M62 Corridor), loc_7 = 0.07 (Runcorn), loc_8 = 0.03 (Warrington UK)
  all locs < 0.50  ← fails
  rejection_reason.choice = "DEAD_LINK"  (confidence 0.23!)
    probabilities: WRONG_COMPANY=0.35, WRONG_TITLE=0.06, WRONG_LOCATION=0.18,
                   WRONG_COUNTRY=0.01, DEAD_LINK=0.36, MULTI_FAIL=0.04
```

The correct answer is `WRONG_COUNTRY`.  The model guessed `DEAD_LINK` because it
cannot see that company=0.99 and title=0.98 already passed.  Confidence 0.23 proves
the model is uncertain — it's guessing.

### Codebase Conventions (must follow)

```python
# Module-level constants expected by the runtime
MODULE_NAME = "job_matcher__match_jobs"
MODULE_TYPE = "filter"  # not "transform"
REJECTION_REASONS = {...}   # set of string constants
ERROR_REASONS = {...}
WARNING_REASONS: set[str] = set()

# Every module tags rows and calls sli_observe once at the end on ALL rows
sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
return ExecutionResult(..., data=passed(prev_data))

# Never print(); use log_event(logger, "info"/"error", event_name, trace_id, **kw)
# Reject with reason from REJECTION_REASONS: reject(row, "WRONG_COMPANY")
```

---

## Implementation Blueprint

### Change 1 — Remove rejection_reason ChoiceQuestion; add `_derive_rejection_reason`

```python
# REMOVE from _build_questions():
questions["rejection_reason"] = ChoiceQuestion(...)   # DELETE

# ADD new helpers above _build_questions():

_OUTSIDE_UK_MARKERS = (
    "united states", "united states of america", "canada", "australia",
    "new zealand", " pa,", " tx,", " ny,", " ca,", " fl,", " va,",
    " al ", " al,",  # US state abbreviations in "city, ST," format
)

def _detect_location_country(location_strings: list[str]) -> str:
    """Return 'United States', 'United Kingdom', or '' (unknown).

    Only fires on unambiguous signals (country names or US state codes).
    Latin-script foreign cities without country suffix → return '' so the
    agent stage can decide.
    """
    lower_strings = [s.lower() for s in location_strings]
    for s in lower_strings:
        if any(m in s for m in _OUTSIDE_UK_MARKERS):
            return "United States"  # simplified; extend if needed
    for s in lower_strings:
        if "united kingdom" in s or " uk" in s or ", gb" in s:
            return "United Kingdom"
    return ""


def _derive_rejection_reason(
    answers: dict,
    asked_title_indices: list[int],
    n_locs: int,
    location_strings: list[str],
) -> str:
    """Deterministic rejection reason; called only when the row is being rejected."""
    company_ans = answers.get("company")
    if not company_ans or company_ans.noul <= _MATCH_THRESHOLD:
        return "WRONG_COMPANY"

    has_title = any(
        (a := answers.get(f"title_{i}")) and a.noul > _MATCH_THRESHOLD
        for i in asked_title_indices
    )
    if not has_title:
        return "WRONG_TITLE"

    # Company + title passed; location failed
    country = _detect_location_country(location_strings)
    if country and country != "United Kingdom":
        return "WRONG_COUNTRY"
    return "WRONG_LOCATION"
```

### Change 2 — Add `location_country` to state; deduplicate `location_strings`; drop `url`

```python
def _job_state(row: dict) -> dict:
    page = row.get("page") or {}
    sj = page.get("structured_job") or {}
    # Deduplicate preserving order (dict trick); avoids sending same string twice to jev
    raw_strings = row.get("location_strings") or []
    location_strings = list(dict.fromkeys(raw_strings))
    return {
        "company":          row.get("resolved_company") or row.get("company") or sj.get("company") or "",
        "title":            row.get("resolved_title")   or row.get("title")   or sj.get("title")   or "",
        "location_strings": location_strings,
        "location_country": _detect_location_country(location_strings),   # NEW
        "is_remote":        bool(row.get("is_remote_hint")),
        "title_tag":        (page.get("title_tag") or "")[:120],
        # NOTE: url intentionally excluded — sanitized feed.example URLs carry no
        # company name signal and the instruction "Consider the company in url" would
        # mislead the model. Re-add only if source_url reliably encodes the company.
    }
```

### Change 3 — Company pre-filter + single-candidate question

```python
# In _process_row(), BEFORE the jev call:

candidate_company = _find_matched_company(state["company"], companies)
if candidate_company is None:
    reject(row, "WRONG_COMPANY")
    return   # no jev call needed

# Build per-row questions (copy base loc+title questions, override company)
row_questions = {k: v for k, v in questions.items() if not k.startswith("company")}
row_questions["company"] = NoulQuestion(
    instructions=(
        f"Does this job page belong to '{candidate_company}'? "
        "Ignore case, a leading 'The', and legal suffixes "
        "(Ltd, plc, Group, Holdings, Corp, UK, Engineering, Systems). "
        "Consider title_tag and title."  # ← no 'url': sanitized feed URLs carry no company name
    ),
    # No criteria= kwarg: criteria is for ChoiceQuestion; NoulQuestion only needs instructions
)
```

### Change 4 — Pre-filter title questions; remove `criteria` from all NoulQuestions

```python
# ADD helper:

_TITLE_SPLIT_RE = re.compile(r"[^a-z0-9\s]")

def _title_word_set(text: str) -> frozenset[str]:
    words = _TITLE_SPLIT_RE.sub(" ", text.lower()).split()
    return frozenset(w.rstrip("s") for w in words if len(w) > 2)

def _relevant_title_indices(job_title: str, titles: list[str]) -> list[int]:
    """Indices of profile titles that share ≥1 word with the job title."""
    job_words = _title_word_set(job_title)
    return [
        i for i, t in enumerate(titles)
        if _title_word_set(t) & job_words
    ]

# In _process_row(), BEFORE the jev call:
asked_title_indices = _relevant_title_indices(state["title"], titles)
# Build per-row questions (remove all title_* from base, add only relevant ones)
row_questions = {k: v for k, v in row_questions.items() if not k.startswith("title_")}
for i in asked_title_indices:
    row_questions[f"title_{i}"] = questions[f"title_{i}"]
```

**Also in `_build_questions`: remove `criteria=` from title and location NoulQuestions.**
`criteria` is semantically meaningful only for `ChoiceQuestion`.  On a `NoulQuestion`
it is ignored by the model but still serialised and sent, burning ~40 tokens per
question.  Remove the kwarg from all `NoulQuestion(...)` calls:

```python
# BEFORE (wasteful):
questions[f"title_{i}"] = NoulQuestion(
    instructions=f"Does the job title contain every word from '{title}'? ...",
    criteria={"true": f"Job title matches '{title}'", "false": f"Job title does NOT match '{title}'"},
)

# AFTER (correct):
questions[f"title_{i}"] = NoulQuestion(
    instructions=f"Does the job title contain every word from '{title}'? ...",
    # No criteria= — NoulQuestion only needs instructions
)

# Same for loc_* questions: remove the criteria= kwarg entirely.
```

### Change 5 — Wire `_derive_rejection_reason` into `_process_row`

Replace the existing `rejection_reason = _get_rejection_reason(answers)` pattern:

```python
# After the jev call returns answers:

# Evaluate company (using candidate found in pre-filter)
company_ans = answers.get("company")
if not company_ans or company_ans.noul <= _MATCH_THRESHOLD:
    reject(row, _derive_rejection_reason(answers, asked_title_indices, len(locations), state["location_strings"]))
    return
# candidate_company is the canonical name (found before jev call, no need for _find_matched_company again)

matched_titles = [
    titles[i] for i in asked_title_indices
    if (a := answers.get(f"title_{i}")) and a.noul > _MATCH_THRESHOLD
]
if not matched_titles:
    reject(row, _derive_rejection_reason(answers, asked_title_indices, len(locations), state["location_strings"]))
    return

matched_locs = [
    locations[i]["name"]
    for i in range(len(locations))
    if (a := answers.get(f"loc_{i}")) and a.noul > _MATCH_THRESHOLD
]
if not matched_locs:
    reject(row, _derive_rejection_reason(answers, asked_title_indices, len(locations), state["location_strings"]))
    return

row["matched_company"]   = candidate_company   # ← use pre-computed value
row["matched_job_title"] = matched_titles
row["matched_location"]  = matched_locs
row["reason"]            = f"jev: company={candidate_company}, titles={matched_titles}, locations={matched_locs}"
row["used_llm"] = True
```

### Change 6 — Remove `_get_rejection_reason` and `ChoiceQuestion` import usage

Delete `_get_rejection_reason()` entirely.  Remove `ChoiceQuestion` from the import
if it is no longer used (check first).

---

## Full list of tasks (implement in order)

```yaml
Task 1:
  MODIFY v2/workers/job_matcher/agent/match_jobs.py:
  - ADD _OUTSIDE_UK_MARKERS constant (tuple of lowercase strings)
  - ADD _detect_location_country(location_strings) -> str
  - ADD _derive_rejection_reason(answers, asked_title_indices, n_locs, location_strings) -> str
  - ADD _title_word_set(text) -> frozenset[str]
  - ADD _relevant_title_indices(job_title, titles) -> list[int]

Task 2:
  MODIFY v2/workers/job_matcher/agent/match_jobs.py:
  - UPDATE _job_state() to include "location_country": _detect_location_country(...)

Task 3:
  MODIFY v2/workers/job_matcher/agent/match_jobs.py:
  - UPDATE _build_questions() to REMOVE the rejection_reason ChoiceQuestion block entirely
  - Keep company, title_*, loc_* questions unchanged in the base questions dict
    (company question in _build_questions can stay as the fallback/base; it will
    be overridden per row in _process_row — OR simplify by removing it from
    _build_questions too and building it fully in _process_row)

  NOTE: Since company question is now per-row (uses candidate_company), remove the
  generic company question from _build_questions entirely. Build it in _process_row.

Task 4:
  MODIFY v2/workers/job_matcher/agent/match_jobs.py:
  - UPDATE _process_row() signature to remove dependency on `questions["rejection_reason"]`
  - At start of _process_row (before jev call):
    1. Compute state = _job_state(row)
    2. candidate_company = _find_matched_company(state["company"], companies)
       → if None: reject(row, "WRONG_COMPANY"); return
    3. asked_title_indices = _relevant_title_indices(state["title"], titles)
    4. Build row_questions:
         - Start from base questions (loc_* only, since company and title_* are per-row)
         - Add company NoulQuestion for candidate_company
         - Add title_i NoulQuestion for i in asked_title_indices
  - Call decide_async with state and row_questions
  - Replace rejection_reason = _get_rejection_reason(answers) with
    _derive_rejection_reason(answers, asked_title_indices, len(locations), state["location_strings"])
  - Use candidate_company directly (skip second _find_matched_company call)

Task 5:
  MODIFY v2/workers/job_matcher/agent/match_jobs.py:
  - DELETE _get_rejection_reason() function entirely
  - DELETE _REJECTION_CRITERIA dict (no longer needed)
  - Remove ChoiceQuestion from import if unused
  - Update REJECTION_REASONS set: keep WRONG_COMPANY, WRONG_TITLE, WRONG_LOCATION,
    WRONG_COUNTRY, MULTI_FAIL; remove DEAD_LINK (dead links are caught by
    filter_dead_links before this module) and NO_MATCH
  - In _build_questions(): remove criteria= kwarg from every NoulQuestion call
    (both title_* and loc_* questions)
  - In per-row company NoulQuestion (built in _process_row): no criteria= kwarg;
    remove "url" from instruction text

Task 6:
  CREATE tests/v2/test_match_jobs.py:
  - Unit tests for all new helpers
  - Integration test using mock jev that verifies per-row question building
  - test_noul_questions_have_no_criteria: verify _build_questions output has
    no criteria field on any NoulQuestion
  - test_location_strings_deduplicated: verify _job_state deduplicates duplicates
  - test_url_not_in_company_instruction: verify the per-row company NoulQuestion
    instruction does not contain the word "url"

```

---

## Validation Loop

### Level 1: Syntax and Types

```bash
# Run from repo root after editing
.venv/bin/python -m ruff check v2/workers/job_matcher/agent/match_jobs.py --fix
.venv/bin/python -m mypy v2/workers/job_matcher/agent/match_jobs.py --ignore-missing-imports

# No errors expected.
```

### Level 2: New Unit Tests

Create `tests/v2/test_match_jobs.py` with the following tests.  Follow the
`make_row()` / `ctx` / `profile` fixtures from `tests/v2/conftest.py`.  Use
`monkeypatch` to replace `decide_async` so tests don't hit the live API.

```python
"""Unit tests for v2 match_jobs module — helper functions and row-level logic."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

# ── _detect_location_country ────────────────────────────────────────────────


def test_detect_country_us_from_state():
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country(["Warrington, PA, United States"]) == "United States"


def test_detect_country_uk_from_suffix():
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country(["Warrington, United Kingdom"]) == "United Kingdom"


def test_detect_country_empty_returns_empty():
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country([]) == ""


def test_detect_country_latin_foreign_city_returns_empty():
    """Latin-script foreign city without country suffix → unknown; agent decides."""
    from v2.workers.job_matcher.agent.match_jobs import _detect_location_country

    assert _detect_location_country(["Birmingham"]) == ""


# ── _derive_rejection_reason ────────────────────────────────────────────────


def _make_noul_answer(noul: float):
    from v2.shared.api_calls.llm import NoulAnswer
    return NoulAnswer(noul=noul)


def test_derive_rejection_wrong_company():
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {"company": _make_noul_answer(0.1)}
    assert _derive_rejection_reason(answers, [0], 2, ["Warrington"]) == "WRONG_COMPANY"


def test_derive_rejection_wrong_title():
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {"company": _make_noul_answer(0.99), "title_0": _make_noul_answer(0.02)}
    assert _derive_rejection_reason(answers, [0], 2, ["Warrington"]) == "WRONG_TITLE"


def test_derive_rejection_wrong_country():
    """US job: company and title pass but location fails → WRONG_COUNTRY."""
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {
        "company":  _make_noul_answer(0.99),
        "title_10": _make_noul_answer(0.98),
    }
    result = _derive_rejection_reason(
        answers,
        asked_title_indices=[10],
        n_locs=12,
        location_strings=["Warrington, PA, United States"],
    )
    assert result == "WRONG_COUNTRY"


def test_derive_rejection_wrong_location_uk_city():
    """UK city not in any profile region → WRONG_LOCATION (not WRONG_COUNTRY)."""
    from v2.workers.job_matcher.agent.match_jobs import _derive_rejection_reason

    answers = {
        "company":  _make_noul_answer(0.99),
        "title_10": _make_noul_answer(0.98),
    }
    result = _derive_rejection_reason(
        answers,
        asked_title_indices=[10],
        n_locs=12,
        location_strings=["London"],
    )
    assert result == "WRONG_LOCATION"


# ── _relevant_title_indices ─────────────────────────────────────────────────


def test_relevant_titles_exact_match():
    from v2.workers.job_matcher.agent.match_jobs import _relevant_title_indices

    titles = ["Controls Engineer", "Electrical Engineer", "CNC Operator"]
    result = _relevant_title_indices("Controls Engineer", titles)
    assert 0 in result   # "Controls Engineer" shares words
    assert 1 in result   # "Electrical Engineer" shares "engineer"
    assert 2 not in result  # "CNC Operator" shares nothing with "controls engineer"


def test_relevant_titles_no_overlap_excluded():
    from v2.workers.job_matcher.agent.match_jobs import _relevant_title_indices

    titles = ["mig welder", "cnc miller", "paint sprayer"]
    result = _relevant_title_indices("Controls Engineer", titles)
    assert result == []


def test_relevant_titles_plural_stripped():
    """'engineers' should match profile title 'engineer'."""
    from v2.workers.job_matcher.agent.match_jobs import _relevant_title_indices

    titles = ["Electrical Engineer"]
    result = _relevant_title_indices("Senior Electrical Engineers", titles)
    assert 0 in result


# ── _job_state includes location_country ────────────────────────────────────


def test_job_state_includes_location_country():
    from v2.workers.job_matcher.agent.match_jobs import _job_state
    from v2.shared.observability.sli_observe import META_OUTCOME

    row = {
        "job_id": "J001",
        "resolved_company": "Aire Calder",
        "resolved_title": "Controls Engineer",
        "location_strings": ["Warrington, PA, United States"],
        "is_remote_hint": False,
        "source_url": "",
        "page": {},
        META_OUTCOME: "pass",
    }
    state = _job_state(row)
    assert "location_country" in state
    assert state["location_country"] == "United States"


# ── _build_questions: no rejection_reason; no criteria on NoulQuestions ────────


def test_build_questions_no_rejection_reason():
    from v2.workers.job_matcher.agent.match_jobs import _build_questions

    questions = _build_questions(
        companies=[],
        titles=["Controls Engineer"],
        locations=[{"name": "Warrington", "type": "sub_region", "includes": [], "country": "United Kingdom"}],
    )
    assert "rejection_reason" not in questions


def test_noul_questions_have_no_criteria():
    """NoulQuestion instances should have no criteria (or criteria=None) — it's for ChoiceQuestion."""
    from ai.ops.experimental import NoulQuestion
    from v2.workers.job_matcher.agent.match_jobs import _build_questions

    questions = _build_questions(
        companies=[],
        titles=["Controls Engineer", "Electrical Engineer"],
        locations=[{"name": "Warrington", "type": "sub_region", "includes": ["Warrington"], "country": "United Kingdom"}],
    )
    for key, q in questions.items():
        if isinstance(q, NoulQuestion):
            # criteria should be absent or None/empty — not a populated dict
            criteria = getattr(q, "criteria", None)
            assert not criteria, f"Question {key!r} has non-empty criteria={criteria!r}"


# ── _job_state: deduplication and url exclusion ─────────────────────────────


def test_job_state_deduplicates_location_strings():
    from v2.workers.job_matcher.agent.match_jobs import _job_state
    from v2.shared.observability.sli_observe import META_OUTCOME

    row = {
        "job_id": "J002",
        "resolved_company": "Aire Calder",
        "resolved_title": "Controls Engineer",
        "location_strings": ["Warrington, PA, United States", "Warrington, PA, United States"],
        "is_remote_hint": False,
        "source_url": "https://feed.example/jobs/s0001435",
        "page": {},
        META_OUTCOME: "pass",
    }
    state = _job_state(row)
    assert state["location_strings"] == ["Warrington, PA, United States"]  # deduplicated


def test_job_state_no_url_key():
    """URL is excluded from state because sanitized feed URLs carry no company signal."""
    from v2.workers.job_matcher.agent.match_jobs import _job_state
    from v2.shared.observability.sli_observe import META_OUTCOME

    row = {
        "job_id": "J003",
        "resolved_company": "Aire Calder",
        "resolved_title": "Controls Engineer",
        "location_strings": [],
        "is_remote_hint": False,
        "source_url": "https://feed.example/jobs/s0001435",
        "page": {},
        META_OUTCOME: "pass",
    }
    state = _job_state(row)
    assert "url" not in state


# ── integration: _process_row rejects US job as WRONG_COUNTRY ────────────────


@pytest.fixture
def us_row():
    from tests.v2.conftest import make_row
    from v2.shared.observability.sli_observe import META_OUTCOME

    row = make_row(
        job_id="J_us_001",
        title="Controls Engineer",
        company="Aire Calder",
        location="Warrington, PA, United States",
    )
    row["resolved_company"] = "Aire Calder"
    row["resolved_title"] = "Controls Engineer"
    row["location_strings"] = ["Warrington, PA, United States"]
    row["is_remote_hint"] = False
    row[META_OUTCOME] = "pass"
    return row


@pytest.fixture
def full_profile():
    """Profile with the 'Aire Calder' company and 'Controls Engineer' title."""
    return {
        "profile_id": "test",
        "companies": [{"name": "Aire Calder", "industry": None}],
        "titles": ["Controls Engineer"],
        "locations": [
            {
                "name": "Warrington",
                "type": "sub_region",
                "includes": ["Warrington", "Runcorn"],
                "country": "United Kingdom",
            }
        ],
    }


@pytest.mark.asyncio
async def test_process_row_us_job_rejected_wrong_country(us_row, full_profile, tmp_path, monkeypatch):
    """A US job (company+title match, location=US) must be rejected as WRONG_COUNTRY."""
    from v2.shared.api_calls.llm import NoulAnswer
    from v2.shared.observability.sli_observe import META_OUTCOME, META_REJECTION_REASON
    from v2.workers.job_matcher.agent.match_jobs import _build_questions, _process_row

    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))

    companies = ["Aire Calder"]
    titles = ["Controls Engineer"]
    locations = full_profile["locations"]
    questions = _build_questions(companies, titles, locations)

    # Mock jev: company matches, title matches, all locations fail
    mock_answers = {
        "company":  NoulAnswer(noul=0.99),
        "title_0":  NoulAnswer(noul=0.98),
        "loc_0":    NoulAnswer(noul=0.01),
    }

    import asyncio
    sem = asyncio.Semaphore(1)
    import logging

    with patch(
        "v2.workers.job_matcher.agent.match_jobs.decide_async",
        new=AsyncMock(return_value=mock_answers),
    ):
        await _process_row(sem, us_row, questions, companies, titles, locations, logging.getLogger(), "t")

    assert us_row[META_OUTCOME] == "rejected"
    assert us_row[META_REJECTION_REASON] == "WRONG_COUNTRY"
```

```bash
# Run new tests
.venv/bin/python -m pytest tests/v2/test_match_jobs.py -v
# Expected: all tests pass
```

### Level 3: Full test suite

```bash
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_llm_cap.py
# Expected: all passing (test_llm_cap.py requires live API key, skip here)
```

---

## Gotchas and Known Constraints

```python
# GOTCHA 1: _MATCH_THRESHOLD is 0.5 — already defined at module level; don't redefine
_MATCH_THRESHOLD = 0.5

# GOTCHA 2: NoulAnswer / ChoiceAnswer come from ai.ops.experimental via llm.py re-export
# Import as: from v2.shared.api_calls.llm import NoulAnswer
# The NoulAnswer dataclass has a single field: noul: float

# GOTCHA 3: _find_matched_company requires ALL tokens of the profile company name to
# appear in the resolved name. If resolve_company passed the job, _find_matched_company
# will almost always return a candidate. But it may return None for edge cases
# (e.g., single-word company that normalizes to empty token set). Handle gracefully.

# GOTCHA 4: _build_questions is called ONCE per profile run (outside the per-row loop).
# After this change, company questions are built per-row inside _process_row. The
# returned questions dict from _build_questions will only contain title_* and loc_*
# questions. Company question is built fresh per row.

# GOTCHA 5: The _REJECTION_CRITERIA dict was used only for the rejection_reason
# ChoiceQuestion. Once that question is removed, delete _REJECTION_CRITERIA too
# (it's dead code). But keep REJECTION_REASONS set (the module contract requires it).

# GOTCHA 6: asked_title_indices must be passed to _derive_rejection_reason so it
# knows which title_i keys to look up in answers. Do NOT iterate range(len(titles))
# for title check — jev only received a subset.

# GOTCHA 7: If asked_title_indices is empty (no title overlap), the row should have
# been rejected by resolve_title earlier. But handle defensively: empty asked_title_indices
# → _derive_rejection_reason returns WRONG_TITLE correctly since the any() comprehension
# over an empty list is False.

# GOTCHA 8: _process_row builds row_questions as a per-row dict. Make sure loc_* 
# questions still come from the base questions dict (they ARE the same for every row).
# Build row_questions as:
#   row_questions = {}
#   for i in asked_title_indices:
#       row_questions[f"title_{i}"] = questions[f"title_{i}"]
#   for k, v in questions.items():
#       if k.startswith("loc_"):
#           row_questions[k] = v
#   row_questions["company"] = NoulQuestion(... candidate_company ...)
# This avoids shallow copy mistakes.

# GOTCHA 9: NoulQuestion criteria= is silently ignored by jev but still serialised
# and sent over the wire. Check the NoulQuestion dataclass definition in
# v2/shared/api_calls/llm.py (it re-exports from ai.ops.experimental). If criteria
# is a required field (not Optional), pass criteria=None or an empty dict — confirm
# by inspecting the dataclass signature before removing it.

# GOTCHA 10: location_strings deduplication must happen BEFORE _detect_location_country
# is called (the country detection iterates the strings). Both calls in _job_state
# receive the deduplicated list.

# GOTCHA 11: Removing "url" from state reduces context for the company check.
# The company instruction currently says "Consider title_tag, url, and title."
# After this change it reads "Consider title_tag and title." The tradeoff is
# acceptable: sanitized feed.example URLs provide zero signal; real production URLs
# (if they contained e.g. "aire-calder.co.uk") would be useful, but the current
# dataset does not have them. If source URLs are ever real, re-add "url" to state
# and the instruction.
```

---

## Final Validation Checklist

- [ ] `rejection_reason` no longer appears in any `questions` dict sent to jev
- [ ] `_get_rejection_reason()` and `_REJECTION_CRITERIA` are deleted
- [ ] `_detect_location_country()` correctly identifies `"Warrington, PA, United States"` → `"United States"`
- [ ] `_derive_rejection_reason()` with US location_strings returns `"WRONG_COUNTRY"`
- [ ] `_relevant_title_indices("Controls Engineer", [...57 titles...])` returns far fewer than 57
- [ ] Company NoulQuestion in `_process_row` lists only one company name (not 300)
- [ ] `_job_state()` includes `"location_country"` key
- [ ] `_job_state()` deduplicates `location_strings` (dict.fromkeys pattern)
- [ ] No `criteria=` kwarg on any `NoulQuestion` call in the file
- [ ] Company instruction text does not contain the word "url"
- [ ] `.venv/bin/python -m pytest tests/v2/test_match_jobs.py -v` → all green
- [ ] `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_llm_cap.py` → all green
- [ ] `.venv/bin/python -m ruff check v2/workers/job_matcher/agent/match_jobs.py` → no errors
- [ ] `.venv/bin/python -m mypy v2/workers/job_matcher/agent/match_jobs.py --ignore-missing-imports` → no errors

---

## Score

**9/10** — All six issues are precisely diagnosed with evidence from a real logged
call.  The implementation path is narrow (one source file, one new test file), every
helper is independently testable, and the validation gates are directly executable.
The 1-point deduction is for the `criteria=` field on `NoulQuestion`: confirm the
dataclass signature in `ai.ops.experimental` before removing it — if the field is
required (not `Optional`), pass `criteria=None` instead of omitting it entirely.
Verify with `pytest --co tests/v2/test_match_jobs.py` before running.
