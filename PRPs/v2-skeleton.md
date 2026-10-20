# PRP: v2 Skeleton — Scaffold with Normalization and Agent Levels

## Goal

Create a complete, runnable skeleton for `v2/` that:

1. Copies `v1/shared/` into `v2/shared/` with updated import paths — the shared runtime is maintained independently in v2 going forward.
2. Writes the **v2 worker from scratch** (no copy from v1) with the correct module contract.
3. Introduces **two new pipeline levels**:
   - `stage_normalise` — deterministic normalization of title, company, and location fields
   - `stage_agent` — LLM-backed fallback resolution for rows that deterministic normalization cannot handle
4. Wires all stages into a 4-stage STAGE_GRAPH in `v2/workers/job_matcher/handler.py`.
5. Provides **stub modules** for all stages: pass-through implementations satisfying the module contract so the pipeline runs end-to-end from day one.
6. Keeps `make test` (v1 tests) green throughout.
7. Adds a `make run-v2` target.

**End state:** `make run-v2` runs without error, writes `runs/<trace_id>/profile_a_matched.jsonl`, and the scaffold is ready for incremental implementation.

**Scope boundary:** `v2/shared/` = copied and adapted from v1. `v2/workers/` = written fresh.

---

## Why

- **v1 is deliberately broken**: 10 known bugs make it miss ~48 of ~50 matches. The fixes need a clean, purpose-built home.
- **Normalization and agent are the solution architecture**: the root cause is data normalization (resolve_job_town drops 99.6% of rows). `stage_normalise` + `stage_agent` is the right layering.
- **Shared independence**: `v2/shared/` diverges freely from v1/shared without breaking v1.
- **Scaffold first**: structure before logic — every stub is a placeholder for a specific bug fix.

---

## What

### Pipeline architecture

```
v2 STAGE_GRAPH
──────────────
stage_clean_jobs      load + flatten into canonical shape
  load_job_feed

stage_normalise       ← NORMALIZATION LEVEL (prepare data before agent matching)
  filter_dead_links     ← fix bug #1: 404/410 jobs removal
  filter_duplicates     ← dedup by job_id (fix v1 title|company dedup bug)
  resolve_location      ← fix bug #2: location string parsing
  resolve_title         ← fix bug #3: scraped title resolution stub
  resolve_company       ← fix bug #5: company name normalization stub

stage_agent           ← AGENT LEVEL (AI matching — implementation TBD)
  (empty for now)

stage_output          ← OUTPUT STAGE
  generate_output       ← writes matched.jsonl (renamed from portal_matches_output)
```

### New row fields added by v2 normalise stage

```python
# After stage_normalise, each row gains:
row["resolved_title"]    # str — best title found (stub: same as row["title"])
row["resolved_company"]  # str — normalized company (stub: same as row["company"])
row["town"]              # str — resolved UK town (same contract as v1 resolve_job_town)
row["region"]            # str
row["country"]           # str
row["used_llm"]          # bool — False initially
```

Agent modules (TBD) will read these normalized fields and set `matched_company`, `matched_job_title`, `matched_location`, `reason` on matched rows. `generate_output` then writes rows that have `matched_company` set.

### Success Criteria

- [ ] `make run-v2` exits 0, writes output file
- [ ] `make test` exits 0 — no regression in v1 tests
- [ ] `ruff check v2/ --fix` exits 0
- [ ] `python -c "from v2.shared.patterns.worker_runtime import ExecutionResult"` succeeds
- [ ] All v2 module files have MODULE_NAME, MODULE_TYPE, REJECTION_REASONS, ERROR_REASONS, WARNING_REASONS, `main()`
- [ ] `tests/v2/__init__.py` exists (empty)
- [ ] No `match_jobs.py` anywhere in v2/ (matching is agent responsibility)

---

## All Needed Context

### Source files to READ (not copy — understand only)

```yaml
- file: v1/shared/patterns/worker_runtime.py
  why: Defines ExecutionResult, StageDefinition, run_stage_loop, run_local_handler —
       these are the runtime primitives every module, stage and handler uses.
       v2/shared/ will be an adapted copy; v2/workers/ code imports from v2.shared.

- file: v1/shared/observability/sli_observe.py
  why: Defines passed(), reject(), sli_observe() — the observability contract
       every module must call sli_observe() ONCE at the end on ALL rows.

- file: v1/shared/patterns/logging.py
  why: get_logger(MODULE_NAME), log_event() — logging pattern every module follows.

- file: v1/workers/job_matcher/modules/load_job_feed.py
  why: REFERENCE for module contract structure (MODULE_NAME/TYPE/REASONS, main(), L1/L2 pattern)
       Write v2 version fresh — do not copy.

- file: v1/workers/job_matcher/modules/match_jobs.py
  why: REFERENCE only — understand the three-gate filter pattern (company → title → location).
       Do NOT recreate match_jobs.py in v2. Matching is the agent's responsibility.

- file: v1/workers/job_matcher/modules/resolve_job_town.py
  why: REFERENCE for resolve_location.py — same field output contract (town/region/country/used_llm).
       Write v2 version fresh in normalization/ folder.

- file: v1/workers/job_matcher/_shared/town_lookup.py
  why: REFERENCE only — TOWNS dict and lookup functions.
       Do NOT copy to v2. resolve_location.py inlines a minimal TOWNS dict directly.

- file: v1/workers/job_matcher/handler.py
  why: REFERENCE for handler pattern — v2 handler has 4 stages instead of 2.

- file: v1/workers/job_matcher/stages/stage_clean_jobs.py
  why: REFERENCE for stage boilerplate (STAGE_NAME, STAGE_GRAPH, schemas, main()).

- file: OUTPUT_FORMAT.json
  why: Canonical matching rules and output field contract.
       Company: fuzzy, across page fields, strip legal suffixes.
       Title: every word present in any order, case/punct insensitive.
       Location: city covers includes; sub_region covers towns inside it; remote covers remote jobs.

- file: NOTES.md
  why: Ground-truth analysis — 10 known v1 bugs, data statistics, pipeline funnel numbers.
       The 10 bugs are the spec for v2 module implementations.
```

### Current codebase tree

```
v1/
  shared/
    api_calls/{__init__,llm}.py
    observability/sli_observe.py
    patterns/{logging,worker_runtime}.py
    schemas/job_matcher/{__init__,v1}.py
    schemas/pipeline_start_takehome/{__init__,v1}.py
  workers/job_matcher/
    handler.py
    _shared/{__init__,town_lookup}.py
    stages/{stage_clean_jobs,stage_match_jobs}.py
    modules/{load_job_feed,normalise_job_rows,drop_duplicate_jobs,
             resolve_job_town,match_jobs,portal_matches_output}.py
tests/
  test_golden.py   test_llm_cap.py
  v1/  (full test suite with xfail tests documenting all 10 v1 bugs)
pyproject.toml
Makefile
```

### Desired codebase tree (new files only)

```
v2/                                       ← ALL NEW
  __init__.py
  shared/                                 ← COPY from v1/shared (3 files need import edits)
    __init__.py
    api_calls/__init__.py
    api_calls/llm.py                      copy unchanged
    observability/__init__.py             new empty
    observability/sli_observe.py          copy + 1 import edit
    patterns/__init__.py
    patterns/logging.py                   copy unchanged
    patterns/worker_runtime.py            copy + 2 import edits
    schemas/__init__.py
    schemas/job_matcher/__init__.py
    schemas/job_matcher/v1.py             copy + 1 import edit
    schemas/pipeline_start_takehome/__init__.py
    schemas/pipeline_start_takehome/v1.py copy unchanged
  workers/                                ← ALL WRITTEN FRESH
    __init__.py
    job_matcher/
      __init__.py
      handler.py                          fresh — 4-stage STAGE_GRAPH
      stages/
        __init__.py
        stage_clean_jobs.py               fresh — 1 module
        stage_normalise.py                fresh — 5 modules (normalization/ folder)
        stage_agent.py                    fresh — empty STAGE_GRAPH (matching TBD)
        stage_output.py                   fresh — 1 module
      modules/                            ← clean + output modules only
        __init__.py
        load_job_feed.py                  fresh — reads JSONL + flattens scraped.* in one step
        generate_output.py                fresh (renamed from portal_matches_output)
      normalization/                      ← NORMALIZATION LEVEL FOLDER
        __init__.py
        filter_dead_links.py              fresh (real impl — moved from modules/)
        filter_duplicates.py              fresh (real impl — renamed from drop_duplicate_jobs)
        resolve_location.py               fresh stub — location string parsing
        resolve_title.py                  fresh stub — title resolution
        resolve_company.py                fresh stub — company normalization
      agent/                              ← AGENT LEVEL FOLDER (AI matching — TBD)
        __init__.py
tests/
  v2/__init__.py                          new empty — ready for future v2 tests
Makefile                                  + run-v2 target
pyproject.toml                            + "v2*" in packages.find
```

### Known Gotchas

```python
# CRITICAL: v2/shared/ imports use "v2." prefix — never "v1."
# Only 3 shared files need edits when copied:
#   v2/shared/observability/sli_observe.py       → 1 change
#   v2/shared/patterns/worker_runtime.py         → 2 changes
#   v2/shared/schemas/job_matcher/v1.py          → 1 change

# CRITICAL: pyproject.toml must include "v2*" in packages.find
# Without this, "from v2.shared..." raises ModuleNotFoundError at runtime.

# CRITICAL: there is NO v2/_shared/ folder — town_lookup is not copied.
# resolve_location.py inlines its own minimal TOWNS dict as a stub.

# CRITICAL: module contract — every module file must have at the top:
MODULE_NAME = "job_matcher__<snake_case_name>"    # used in SLI events
MODULE_TYPE = "transform" | "filter"
REJECTION_REASONS: set[str] = {"REASON_A", ...}  # or set() if no rejections
ERROR_REASONS: set[str] = set()
WARNING_REASONS: set[str] = set()

# CRITICAL: sli_observe must be called on ALL rows (passed + rejected)
# WRONG: sli_observe(kept, ...)
# RIGHT: sli_observe(rows, ...)  then return kept

# GOTCHA: stub modules must set META_OUTCOME = "pass" on rows that arrive without it
# load_job_feed sets it; all downstream modules assume it's set.
# Stubs that don't filter can just pass prev_data through without touching META_OUTCOME.

# GOTCHA: resolve_location must produce row["town"], row["region"], row["country"], row["used_llm"]
# Agent modules and generate_output read row["town"] — this field name must not change.

# GOTCHA: filter_dead_links and filter_duplicates are NOT stubs — implement them for real.
# They live in normalization/, not modules/. Their module paths in STAGE_GRAPH reflect this:
#   "v2.workers.job_matcher.normalization.filter_dead_links"

# GOTCHA: generate_output must write the output file and return artifacts={"output_path": str(out)}
# The handler's run_pipeline() reads context["output_path"] from this artifact — it's contract-critical.
# Skeleton writes 0 matched rows because agent stage is empty — that is expected behavior.

# GOTCHA: stage boilerplate — every stage.py has:
#   STAGE_NAME, STAGE_GRAPH, INPUT_CONTEXT_SCHEMA, OUTPUT_CONTEXT_SCHEMA, main()
# The schemas only need to declare fields the stage actually uses/produces.
# Minimal safe schema: just require trace_id in both input and output.

# GOTCHA: normalization/ and agent/ are sibling folders to modules/ inside job_matcher/
# Module paths in each stage's STAGE_GRAPH must use the correct subfolder package:
#   normalization: "v2.workers.job_matcher.normalization.resolve_location"
#   agent:         (empty for now — STAGE_GRAPH = {})
#   modules:       "v2.workers.job_matcher.modules.load_job_feed"
# All three folders need their own __init__.py to be importable packages.

# GOTCHA: stage_agent has an empty STAGE_GRAPH — run_stage_loop() handles this gracefully
# (it simply iterates over zero nodes and returns prev_data unchanged).
```

---

## Implementation Blueprint

### Tasks in order

```yaml
Task 0: MODIFY pyproject.toml
  - FIND: include = ["v1*"]
  - REPLACE: include = ["v1*", "v2*"]

Task 1: MODIFY Makefile
  - ADD after the "run:" target:
      run-v2:
          $(BIN)/python -m v2.workers.job_matcher.handler

Task 2: CREATE v2/shared/ (copy from v1 with targeted import edits)
  Copy unchanged (no internal v1 imports):
    v2/__init__.py                                         (empty)
    v2/shared/__init__.py                                  (empty)
    v2/shared/api_calls/__init__.py                        (empty)
    v2/shared/api_calls/llm.py                             (copy v1 unchanged)
    v2/shared/observability/__init__.py                    (empty — v1 lacks this, create it)
    v2/shared/patterns/__init__.py                         (empty)
    v2/shared/patterns/logging.py                          (copy v1 unchanged)
    v2/shared/schemas/__init__.py                          (empty)
    v2/shared/schemas/job_matcher/__init__.py               (copy v1 unchanged)
    v2/shared/schemas/pipeline_start_takehome/__init__.py  (copy v1 unchanged)
    v2/shared/schemas/pipeline_start_takehome/v1.py        (copy v1 unchanged)

  Copy with import edits:
    v2/shared/observability/sli_observe.py
      CHANGE: from v1.shared.patterns.worker_runtime import run_dir
           →  from v2.shared.patterns.worker_runtime import run_dir

    v2/shared/patterns/worker_runtime.py
      CHANGE: from v1.shared.api_calls import llm
           →  from v2.shared.api_calls import llm
      CHANGE: from v1.shared.patterns.logging import get_logger, log_event
           →  from v2.shared.patterns.logging import get_logger, log_event

    v2/shared/schemas/job_matcher/v1.py
      CHANGE: from v1.shared.schemas.pipeline_start_takehome.v1 import PIPELINE_START_TAKEHOME_SCHEMA
           →  from v2.shared.schemas.pipeline_start_takehome.v1 import PIPELINE_START_TAKEHOME_SCHEMA

Task 3: CREATE v2/workers/ empty __init__.py files
    v2/workers/__init__.py
    v2/workers/job_matcher/__init__.py
    v2/workers/job_matcher/stages/__init__.py
    v2/workers/job_matcher/modules/__init__.py
    v2/workers/job_matcher/normalization/__init__.py     ← NEW package
    v2/workers/job_matcher/agent/__init__.py             ← NEW package

Task 4: CREATE v2/workers/job_matcher/modules/load_job_feed.py  (fresh)
  - Reads jobs_raw.jsonl; rejects INVALID_JSON / NOT_AN_OBJECT / MALFORMED_ROW
  - Immediately flattens scraped.{title,company,location,salary} + page into canonical shape
  - MODULE_TYPE = "transform"
  - See pseudocode below

Task 5: CREATE v2/workers/job_matcher/normalization/filter_dead_links.py  (fresh — real impl)
  - Lives in normalization/ folder (data quality gate before resolution)
  - Rejects rows where page.http_status in (404, 410)
  - REJECTION_REASONS = {"DEAD_LINK"}
  - See pseudocode below

Task 6: CREATE v2/workers/job_matcher/normalization/filter_duplicates.py  (fresh)
  - Lives in normalization/ folder
  - Deduplicates by job_id  ← v1 bug was title|company; v2 uses job_id from day 1
  - REJECTION_REASONS = {"DUPLICATE"}
  - See pseudocode below

Task 7: CREATE v2/workers/job_matcher/normalization/resolve_location.py  (fresh stub)
  - Lives in normalization/ folder
  - Parses location string → town/region/country
  - Rejects UNKNOWN_LOCATION if cannot resolve
  - Stub: inlines a minimal TOWNS dict (no _shared dependency) as a temporary fallback
  - TODO: suffix-stripping, structured_job fallback, remote detection
  - See pseudocode below

Task 8: CREATE v2/workers/job_matcher/normalization/resolve_title.py  (fresh stub)
  - Lives in normalization/ folder
  - Sets row["resolved_title"] = row.get("title", "")
  - No rejections; pure pass-through transform
  - TODO: structured_job.title > title_tag > h1 > scraped.title priority chain

Task 9: CREATE v2/workers/job_matcher/normalization/resolve_company.py  (fresh stub)
  - Lives in normalization/ folder
  - Sets row["resolved_company"] = row.get("company", "")
  - No rejections; pure pass-through transform
  - TODO: multi-field lookup + legal suffix stripping

Task 10: CREATE v2/workers/job_matcher/agent/__init__.py  (empty)
  - Folder exists and is a Python package — ready for AI agent matching modules
  - No modules added yet; matching implementation TBD

Task 11: CREATE v2/workers/job_matcher/modules/generate_output.py  (fresh)
  - Renamed from portal_matches_output
  - Writes runs/<trace_id>/<output_prefix>_matched.jsonl (one JSON line per matched row)
  - Matched rows = rows that have "matched_company" set (by agent stage, TBD)
  - CONTRACT: must return artifacts={"output_path": str(out)}
  - Output shape per OUTPUT_FORMAT.json: job_id, profile_id, matched_company,
    matched_job_title, matched_location, reason, used_llm
  - See pseudocode below

Task 12: CREATE v2/workers/job_matcher/stages/stage_clean_jobs.py  (fresh)
  - 1 module: load_job_feed

Task 13: CREATE v2/workers/job_matcher/stages/stage_normalise.py  (fresh — NORMALIZATION LEVEL)
  - 5 modules: filter_dead_links, filter_duplicates, resolve_location, resolve_title, resolve_company
  - Order matters: filter dead links first, then dedup, then resolve fields

Task 14: CREATE v2/workers/job_matcher/stages/stage_agent.py  (fresh — AGENT LEVEL)
  - STAGE_GRAPH = {}  (empty — AI matching implementation TBD)

Task 15: CREATE v2/workers/job_matcher/stages/stage_output.py  (fresh)
  - 1 module: generate_output

Task 16: CREATE v2/workers/job_matcher/handler.py  (fresh)
  - HANDLER_NAME = "job_matcher"; VERSION = "v2.0.0"
  - 4-stage STAGE_GRAPH

Task 17: CREATE tests/v2/__init__.py  (empty)
```

---

### Per-task pseudocode

```python
# ── Task 4: load_job_feed.py ──────────────────────────────────────────
# Reads JSONL and immediately flattens scraped.* into canonical shape.
# Combining load + flatten avoids a pointless two-step where both always run together.
MODULE_NAME = "job_matcher__load_job_feed"
MODULE_TYPE = "transform"
REJECTION_REASONS = {"INVALID_JSON", "NOT_AN_OBJECT", "MALFORMED_ROW"}

def _parse_salary(value) -> int | None:
    # TODO: handle "£50K", "45,000", range strings
    if value is None or value == "":
        return None
    try:
        return int(str(value).replace("£", "").replace(",", "").strip())
    except ValueError:
        return None

def main(context, prev_data):
    trace_id = context.get("trace_id")
    start_time = time.time()
    rows: list[dict] = []
    with Path(context["jobs_path"]).open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                rows.append({"_line": line_no, META_OUTCOME: "rejected",
                             META_REJECTION_REASON: "INVALID_JSON"})
                continue
            if not isinstance(raw, dict):
                rows.append({"_line": line_no, META_OUTCOME: "rejected",
                             META_REJECTION_REASON: "NOT_AN_OBJECT"})
                continue
            scraped = raw.get("scraped")
            if not isinstance(scraped, dict):
                rows.append({**raw, META_OUTCOME: "rejected",
                             META_REJECTION_REASON: "MALFORMED_ROW"})
                continue
            rows.append({
                "job_id":     raw["job_id"],
                "title":      scraped.get("title", "").strip(),
                "company":    scraped.get("company", "").strip(),
                "location":   scraped.get("location", "").strip(),
                "salary_gbp": _parse_salary(scraped.get("salary")),
                "source_url": raw.get("source_url") or "",
                "page":       raw.get("page") or {},
                META_OUTCOME: "pass",
            })
    sli_observe(rows, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(trace_id=trace_id,
                           script_span_id=f"{MODULE_NAME}_{trace_id}",
                           data=passed(rows), artifacts={}, metrics={})

# ── Task 5: normalization/filter_dead_links.py ───────────────────────
# File: v2/workers/job_matcher/normalization/filter_dead_links.py
MODULE_NAME = "job_matcher__filter_dead_links"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"DEAD_LINK"}

def main(context, prev_data):
    trace_id = context.get("trace_id")
    start_time = time.time()
    for row in prev_data:
        if row.get("page", {}).get("http_status") in (404, 410):
            reject(row, "DEAD_LINK")
    kept = passed(prev_data)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(trace_id=trace_id,
                           script_span_id=f"{MODULE_NAME}_{trace_id}",
                           data=kept, artifacts={}, metrics={})

# ── Task 6: normalization/filter_duplicates.py ──────────────────────
# File: v2/workers/job_matcher/normalization/filter_duplicates.py
MODULE_NAME = "job_matcher__filter_duplicates"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"DUPLICATE"}

def main(context, prev_data):
    trace_id = context.get("trace_id")
    start_time = time.time()
    seen: set[str] = set()
    for row in prev_data:
        key = row["job_id"]           # v2 fix: dedup by job_id, not title|company
        if key in seen:
            reject(row, "DUPLICATE")
        seen.add(key)
    kept = passed(prev_data)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(trace_id=trace_id,
                           script_span_id=f"{MODULE_NAME}_{trace_id}",
                           data=kept, artifacts={}, metrics={})

# ── Task 7: normalization/resolve_location.py ────────────────────────
# File: v2/workers/job_matcher/normalization/resolve_location.py
MODULE_NAME = "job_matcher__resolve_location"
MODULE_TYPE = "filter"
REJECTION_REASONS = {"UNKNOWN_LOCATION"}

# Stub: inline minimal TOWNS dict — no _shared dependency.
# TODO: replace with proper suffix-stripping + structured_job fallback + remote detection.
_UK = "United Kingdom"
_TOWNS: dict[str, dict] = {
    name.lower(): {"town": name, "region": region, "country": _UK}
    for region, names in {
        "North West England": ["Liverpool", "Manchester", "Warrington", "Chester",
                               "Bolton", "Runcorn", "Widnes", "Salford", "Preston",
                               "Lancaster", "Wigan", "Stockport"],
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

def main(context, prev_data):
    trace_id = context.get("trace_id")
    start_time = time.time()
    for row in prev_data:
        # TODO: before exact lookup, try:
        #   1. Strip ", United Kingdom" / ", UK" / ", GB" suffixes
        #   2. "N Locations" placeholder → consult row["page"]["structured_job"]["locations"]
        #   3. Address strings → extract city token
        #   4. Remote keywords → match remote profile locations
        place = _lookup(row.get("location", ""))
        if place is None:
            reject(row, "UNKNOWN_LOCATION")
            continue
        row.update(town=place["town"], region=place["region"],
                   country=place["country"], used_llm=False)
    kept = passed(prev_data)
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(trace_id=trace_id,
                           script_span_id=f"{MODULE_NAME}_{trace_id}",
                           data=kept, artifacts={}, metrics={})

# ── Task 8: normalization/resolve_title.py (stub) ────────────────────
# File: v2/workers/job_matcher/normalization/resolve_title.py
MODULE_NAME = "job_matcher__resolve_title"
MODULE_TYPE = "transform"
REJECTION_REASONS: set[str] = set()

def main(context, prev_data):
    trace_id = context.get("trace_id")
    start_time = time.time()
    for row in prev_data:
        # TODO: page.structured_job.title > page.title_tag > page.h1 > scraped.title
        row["resolved_title"] = row.get("title", "")
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(trace_id=trace_id,
                           script_span_id=f"{MODULE_NAME}_{trace_id}",
                           data=prev_data, artifacts={}, metrics={})

# ── Task 9: normalization/resolve_company.py (stub) ──────────────────
# File: v2/workers/job_matcher/normalization/resolve_company.py
# Identical boilerplate to resolve_title; sets row["resolved_company"] = row.get("company", "")
# TODO: page.structured_job.company > page.h1 > scraped; strip legal suffixes

# ── Task 10: agent/ folder ───────────────────────────────────────────
# Only agent/__init__.py is created. No module files yet — AI matching implementation TBD.
# Agent modules will read resolved_title, resolved_company, town, region, country from each row
# and set: row["matched_company"], row["matched_job_title"], row["matched_location"], row["reason"]

# ── Task 11: modules/generate_output.py ──────────────────────────────
# File: v2/workers/job_matcher/modules/generate_output.py
# Renamed from portal_matches_output
MODULE_NAME = "job_matcher__generate_output"
MODULE_TYPE = "transform"
REJECTION_REASONS: set[str] = set()

def _record(row, profile_id):
    return {
        "job_id":          row["job_id"],
        "profile_id":      profile_id,
        "matched_company": row["matched_company"],
        "matched_job_title": row["matched_job_title"],
        "matched_location": row["matched_location"],
        "reason":          row["reason"],
        "used_llm":        bool(row.get("used_llm")),
    }

def main(context, prev_data):
    trace_id = context.get("trace_id")
    start_time = time.time()
    out = run_dir(trace_id) / f"{context['output_prefix']}_matched.jsonl"
    # Write only rows that the agent stage matched (have matched_company set)
    matched = [r for r in prev_data if r.get("matched_company")]
    with out.open("w", encoding="utf-8") as f:
        for row in matched:
            f.write(json.dumps(_record(row, context["profile"]["profile_id"]),
                               ensure_ascii=False) + "\n")
    sli_observe(prev_data, MODULE_NAME, start_time, trace_id)
    return ExecutionResult(trace_id=trace_id,
                           script_span_id=f"{MODULE_NAME}_{trace_id}",
                           data=matched,
                           artifacts={"output_path": str(out)},
                           metrics={})

# ── Task 12: stage_clean_jobs.py ──────────────────────────────────────
from v2.shared.patterns.worker_runtime import StageDefinition, run_stage_loop
STAGE_NAME = "stage_clean_jobs"
STAGE_GRAPH = {
    "load_job_feed": StageDefinition("load_job_feed", "v2.workers.job_matcher.modules.load_job_feed"),
}
INPUT_CONTEXT_SCHEMA  = {"version": "v2.0.0", "domain": "context", "fields": {"trace_id": {"type": str, "nullable": False}, "jobs_path": {"type": str, "nullable": False}}}
OUTPUT_CONTEXT_SCHEMA = {"version": "v2.0.0", "domain": "context", "fields": {"trace_id": {"type": str, "nullable": False}}}
def main(context, prev_data): return run_stage_loop(STAGE_NAME, STAGE_GRAPH, context, prev_data)

# ── Task 13: stage_normalise.py ───────────────────────────────────────
STAGE_NAME = "stage_normalise"
STAGE_GRAPH = {
    "filter_dead_links":   StageDefinition("filter_dead_links",   "v2.workers.job_matcher.normalization.filter_dead_links"),
    "filter_duplicates": StageDefinition("filter_duplicates", "v2.workers.job_matcher.normalization.filter_duplicates"),
    "resolve_location":    StageDefinition("resolve_location",    "v2.workers.job_matcher.normalization.resolve_location"),
    "resolve_title":       StageDefinition("resolve_title",       "v2.workers.job_matcher.normalization.resolve_title"),
    "resolve_company":     StageDefinition("resolve_company",     "v2.workers.job_matcher.normalization.resolve_company"),
}

# ── Task 14: stage_agent.py ───────────────────────────────────────────
STAGE_NAME = "stage_agent"
STAGE_GRAPH = {}   # empty — AI matching implementation TBD

# ── Task 15: stage_output.py ─────────────────────────────────────────
STAGE_NAME = "stage_output"
STAGE_GRAPH = {
    "generate_output": StageDefinition("generate_output", "v2.workers.job_matcher.modules.generate_output"),
}

# ── Task 16: handler.py ───────────────────────────────────────────────
from v2.shared.patterns.worker_runtime import StageDefinition, run_local_handler
from v2.shared.schemas.job_matcher.v1 import JOB_MATCHER_SCHEMA as OUTPUT_CONTEXT_SCHEMA
from v2.shared.schemas.pipeline_start_takehome.v1 import PIPELINE_START_TAKEHOME_SCHEMA as INPUT_CONTEXT_SCHEMA

HANDLER_NAME = "job_matcher"
VERSION = "v2.0.0"
STAGE_GRAPH = {
    "stage_clean_jobs": StageDefinition("stage_clean_jobs", "v2.workers.job_matcher.stages.stage_clean_jobs"),
    "stage_normalise":  StageDefinition("stage_normalise",  "v2.workers.job_matcher.stages.stage_normalise"),
    "stage_agent":      StageDefinition("stage_agent",      "v2.workers.job_matcher.stages.stage_agent"),
    "stage_output":     StageDefinition("stage_output",     "v2.workers.job_matcher.stages.stage_output"),
}
if __name__ == "__main__":
    sys.exit(run_local_handler(STAGE_GRAPH, INPUT_CONTEXT_SCHEMA, OUTPUT_CONTEXT_SCHEMA, HANDLER_NAME))
```

---

## Validation Loop

### Level 1: Import sanity

```bash
# After all files created:
.venv/bin/python -c "from v2.shared.patterns.worker_runtime import ExecutionResult; print('shared OK')"
.venv/bin/python -c "from v2.workers.job_matcher import handler; print(handler.VERSION)"
# Expected: shared OK / v2.0.0
```

### Level 2: Style

```bash
.venv/bin/python -m ruff check v2/ --fix
# Expected: 0 errors
```

### Level 3: Pipeline smoke test

```bash
make run-v2
# Expected: exits 0, prints match count, writes runs/<ts>/profile_a_matched.jsonl
# Note: skeleton produces few/no matches (resolve_location is same stub logic as v1)
```

### Level 4: Regression

```bash
make test
# Expected: all PASS or XFAIL — zero FAILED/ERROR (v1 tests unchanged)
```

### Level 5: Module contract check

```bash
# Check all module locations: modules/, normalization/ (agent/ has no module files yet)
for f in v2/workers/job_matcher/modules/*.py \
          v2/workers/job_matcher/normalization/*.py; do
  [[ "$f" == *__init__* ]] && continue
  echo "=== $f ==="
  grep -E "^MODULE_NAME|^MODULE_TYPE|^REJECTION_REASONS|^def main" "$f"
done
# Expected: all 4 lines present in every module file (7 files total)
# modules/: load_job_feed, generate_output
# normalization/: filter_dead_links, filter_duplicates, resolve_location, resolve_title, resolve_company
```

---

## Final Validation Checklist

- [ ] `make run-v2` exits 0 with output file written
- [ ] `make test` exits 0 (all v1 tests PASS/XFAIL — no regression)
- [ ] `ruff check v2/ --fix` exits 0
- [ ] `python -c "from v2.shared.patterns.worker_runtime import ExecutionResult"` succeeds
- [ ] `python -c "from v2.workers.job_matcher import handler; print(handler.VERSION)"` prints `v2.0.0`
- [ ] All v2 module files have MODULE_NAME, MODULE_TYPE, REJECTION_REASONS, ERROR_REASONS, WARNING_REASONS, main()
- [ ] `v2/shared/` has zero references to `v1.` anywhere
- [ ] `v2/workers/` has zero references to `v1.` anywhere
- [ ] `v2/workers/job_matcher/normalization/__init__.py` exists (empty)
- [ ] `v2/workers/job_matcher/agent/__init__.py` exists (empty)
- [ ] No `v2/workers/job_matcher/_shared/` folder exists
- [ ] No `match_jobs.py` anywhere in v2/ (matching is agent responsibility — not rule-based)
- [ ] `normalization/resolve_location.py` inlines its own `_TOWNS` dict (no _shared import)
- [ ] `normalization/filter_dead_links.py` path in stage = `"v2.workers.job_matcher.normalization.filter_dead_links"`
- [ ] `normalization/filter_duplicates.py` path in stage = `"v2.workers.job_matcher.normalization.filter_duplicates"`
- [ ] `normalization/resolve_location.py` path in stage = `"v2.workers.job_matcher.normalization.resolve_location"`
- [ ] `agent/` folder has only `__init__.py` — no module files yet
- [ ] `normalization/filter_dead_links.py` rejects 404 and 410 — real implementation, not pass-through
- [ ] `normalization/filter_duplicates.py` deduplicates by `row["job_id"]` (not title|company)
- [ ] `modules/generate_output.py` returns `artifacts={"output_path": str(out)}`
- [ ] `modules/generate_output.py` writes only rows with `matched_company` set
- [ ] `handler.py` STAGE_GRAPH has exactly 4 stages: clean, normalise, agent, output
- [ ] `stages/stage_output.py` exists (not stage_match_jobs)
- [ ] `pyproject.toml` include = ["v1*", "v2*"]
- [ ] `tests/v2/__init__.py` exists (empty)

---

## Anti-Patterns to Avoid

- ❌ Don't copy v1 worker modules and update imports — write fresh
- ❌ Don't import from `v1.` anywhere in `v2/`
- ❌ Don't modify any file under `v1/` or `tests/v1/`
- ❌ Don't skip sli_observe() in any module — even pass-through stubs
- ❌ Don't add any module files to `agent/` yet — the folder is a placeholder only
- ❌ Don't put filter_dead_links or filter_duplicates in modules/ — they live in normalization/
- ❌ Don't create match_jobs.py anywhere — matching is the agent's responsibility
- ❌ Don't change the `row["town"]` field name — agent modules will read it directly
- ❌ Don't forget `artifacts={"output_path": str(out)}` in generate_output — the handler requires it

---

## Architecture Notes (for future PRPs)

### What each stub becomes eventually

| Module                              | Fixes                                                       | v1 bug #       |
| ----------------------------------- | ----------------------------------------------------------- | -------------- |
| `normalization/filter_dead_links` | **Done here** — 404/410 removal                      | #1             |
| `normalization/filter_duplicates` | **Fixed here** — job_id dedup (not title\|company)   | #10            |
| `normalization/resolve_location`  | Suffix stripping, structured_job fallback, remote detection | #2, #6, #7     |
| `normalization/resolve_title`     | structured_job.title > title_tag > h1 priority chain        | #3             |
| `normalization/resolve_company`   | Multi-field lookup + legal suffix strip                     | #5             |
| `agent/` (TBD)                    | AI matching: company + title + location (all 3 gates)       | #4, #5 partial |
| `modules/load_job_feed`           | Robust `_parse_salary` (stubbed inline — expand later)      | #8, #9         |

Two of the ten v1 bugs are fixed in this skeleton (bugs #1, #10). Three normalization stubs (#2, #3, #5) need implementation. The agent stage (bugs #4, #5 matching) is the follow-up PRP after normalization is complete.

---

**PRP Confidence Score: 9/10**

All 36+ files are identified precisely. Import-path rules are explicit. The shared copy list and edit list are complete and non-overlapping. The only execution risk is a missed `v1.` reference inside a worker file — caught immediately by Level 1 import validation and the module contract check.
