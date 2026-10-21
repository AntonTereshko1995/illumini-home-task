# PRP: v2 Job Matcher — Complete Implementation

## Goal

Implement a production-quality v2 job matcher that:

1. Normalization = soft pre-filter using profile data (not hardcoded dicts)
2. Implements the full matching agent (company + title + location + LLM batch for location)
3. Processes 200 000 jobs in < 20 minutes via configurable chunked parallel workers
4. Uses Jev (Vercel AI Gateway) as the LLM provider — calls are parallel across chunks
5. Generates a markdown summary report at the end of each run

The output of a successful run is:
- `runs/<trace_id>/profile_a_matched.jsonl` — one JSON line per matched job
- `runs/<trace_id>/report.md` — pipeline statistics + matched job list

---

## Why

- v1 matches **0 of 11** labelled YES jobs — all lost at `resolve_job_town` (tiny hardcoded dict, exact match only).
- v2 stubs are pass-through only — no normalization, no matching, no parallelism.
- The private test dataset expects ≥ 90 % agreement with production; v1 gets 0 %.
- The task requires 200 000 jobs in 20 minutes; the current single-threaded pipeline cannot scale.

---

## What

### Matching rules (from `OUTPUT_FORMAT.json` — do NOT relax these)

| Signal | Rule |
|--------|------|
| **Company** | Fuzzy: ignore case/punctuation/leading "The"/legal suffixes (Ltd, plc, Group, Holdings, International, UK, Limited, Engineering, Services, Solutions, Systems, Technologies, Co). |
| **Title** | Every word of the profile title appears in the job's resolved title in any order, ignoring case, punctuation, trailing plural *s*. One job can match multiple profile titles. |
| **Location** | A `city` covers its own name + `includes`. A `sub_region` covers its name + `includes`. `remote` covers jobs the employer explicitly marks remote/home-based in that country. Multiple job locations: pass if **any** matches. Jobs in a different country never match. |
| **Live** | HTTP 404 or 410 → rejected unconditionally. |
| **Output** | `matched_job_title` and `matched_location` list **every** profile entry that matched, spelled exactly as in the profile. |

### Architecture overview

```
handler.py
  │
  ├─ load_job_feed (serial, I/O)
  │    └─ all 200k rows in memory
  │
  ├─ split into N chunks  (CHUNK_SIZE env var, default 1000)
  │
  └─ ThreadPoolExecutor (LLM calls are network I/O → real parallelism, GIL releases)
       │
       ├─ chunk_1 ──► stage_normalise ──► pre_filter ──► LLM batch ──► exact_match ─┐
       ├─ chunk_2 ──► stage_normalise ──► pre_filter ──► LLM batch ──► exact_match  ├─► merge
       └─ chunk_N ──► stage_normalise ──► pre_filter ──► LLM batch ──► exact_match ─┘
                                                              ▲
                                              threading.Lock only on budget file read/write
                                              (not on the API call itself → true parallelism)
       │
       ├─ stage_output  (serial, I/O)
       └─ stage_report  (serial)
```

### Normalization = soft pre-filter

Each normalization module has **two responsibilities**:
1. Extract the best available signal (priority chain across page fields)
2. Soft pre-filter: reject rows where NO token from ANY source even *could* match the profile

The profile itself is the reference — no hardcoded city/company dictionaries.

```
resolve_company:  build profile_company_tokens from profile["companies"]
                  reject if resolved_company shares no token with profile_company_tokens
                  → rejects ~30% irrelevant jobs early

resolve_title:    build profile_title_words from profile["titles"]
                  reject if resolved_title shares no word with profile_title_words
                  → rejects ~40% more

resolve_location: build profile_city_set from all profile["locations"][*].includes
                  reject if NO raw location string contains ANY profile city token
                  AND no remote keywords
                  → rejects most of the rest
```

After normalization, `stage_agent` receives only **genuine candidates** (~2-4k from 200k).

### Key data facts (from NOTES.md analysis)

- 1 529 raw jobs; `visible_text` is **empty across the entire dataset** — do not search body text.
- Fill rates: `scraped.title` 100 %, `scraped.company` 100 %, `scraped.location` 72.5 %, `page.title_tag` 39.8 %, `page.structured_job` 27.1 %, `page.h1` 16 %.
- 404 = 46 jobs, 410 = 129 jobs → filter first, saves 11.5 % of work.
- Location formats in feed: `"City, United Kingdom"` 37 %, bare city 30 %, empty 27.5 %, `"N Locations"` placeholder 21 %, hybrid/remote strings.
- `scraped.title` frequently abbreviated (`"HC engineer"` → `"HV Commissioning Engineer"`); use page signals first.
- `scraped.company` often wrong; `structured_job.company` is more reliable when present.

---

## All Needed Context

### Documentation & References

```yaml
- url: https://vercel.com/ai-gateway/models/jev
  why: Model page for Jev — get exact model ID, pricing (USD per M tokens)

- url: https://vercel.com/docs/ai-gateway
  why: Auth method (Bearer VERCEL_API_KEY), base URL, request format, rate limits

- url: https://platform.openai.com/docs/api-reference/chat
  why: Vercel AI Gateway is OpenAI-compatible — same JSON format

- file: v2/shared/api_calls/llm.py
  why: Add Jev provider; follow _send/_guard/_call pattern; add threading.Lock

- file: v2/workers/job_matcher/normalization/filter_dead_links.py
  why: Canonical filter module pattern (reject/passed/sli_observe)

- file: v2/workers/job_matcher/normalization/filter_duplicates.py
  why: Canonical filter module pattern

- file: v2/workers/job_matcher/normalization/resolve_location.py
  why: Current stub — replace entirely; keep MODULE_NAME/MODULE_TYPE/REJECTION_REASONS

- file: v2/shared/observability/sli_observe.py
  why: reject(), passed(), sli_observe() must be called correctly

- file: v2/shared/patterns/worker_runtime.py
  why: ExecutionResult, StageDefinition, run_dir — all workers use these

- file: v2/workers/job_matcher/handler.py
  why: Add chunk splitting + ThreadPoolExecutor here

- file: v2/workers/job_matcher/stages/stage_agent.py
  why: Empty STAGE_GRAPH — add match_jobs module

- file: data/user_search_inputs/profile_a/location_searches.json
  why: Profile city lists — the reference for resolve_location pre-filter

- file: data/user_search_inputs/profile_a/job_title_searches.json
  why: 57 profile titles — reference for resolve_title pre-filter

- file: data/user_search_inputs/profile_a/company_searches.json
  why: 408 companies — reference for resolve_company pre-filter

- file: data/labelled_sample.jsonl
  why: 60 labelled jobs (11 YES, 49 NO) — integration test ground truth

- file: OUTPUT_FORMAT.json
  why: Canonical matching rules and output schema
```

### Current codebase tree (v2 relevant)

```
v2/
  shared/
    api_calls/llm.py              ← add Jev + threading.Lock
    observability/sli_observe.py
    patterns/worker_runtime.py
  workers/job_matcher/
    agent/__init__.py              ← empty; add modules here
    modules/
      load_job_feed.py             ← done
      generate_output.py           ← done
    normalization/
      filter_dead_links.py         ← done
      filter_duplicates.py         ← done
      resolve_company.py           ← STUB → replace with soft pre-filter
      resolve_location.py          ← STUB → replace with soft pre-filter
      resolve_title.py             ← STUB → replace with soft pre-filter
    stages/
      stage_agent.py               ← empty STAGE_GRAPH → fill
      stage_clean_jobs.py          ← done
      stage_normalise.py           ← done (order: dead_links, dupes, company, title, location)
      stage_output.py              ← done
    handler.py                     ← add chunk splitting + ThreadPoolExecutor
tests/v2/__init__.py               ← add tests here
```

### Desired codebase tree (additions)

```
v2/workers/job_matcher/
  agent/
    __init__.py
    company_matcher.py      ← NEW: normalize + fuzzy match
    title_matcher.py        ← NEW: word-set match
    location_matcher.py     ← NEW: profile city → location name
    match_jobs.py           ← NEW: stage_agent module; LLM batch for location
  report/
    __init__.py
    generate_report.py      ← NEW: writes runs/<trace>/report.md
  chunk_runner.py           ← NEW: split + ThreadPoolExecutor orchestration

tests/v2/
  conftest.py
  test_resolve_company.py
  test_resolve_title.py
  test_resolve_location.py
  test_company_matcher.py
  test_title_matcher.py
  test_location_matcher.py
  test_match_jobs.py
  test_labelled_sample.py   ← integration: recall ≥ 9/11
```

### Known Gotchas

```python
# CRITICAL: threading.Lock must wrap budget FILE read+write, NOT the API call.
# Lock: check_budget() + write_llm_log(). Release before making the HTTP request.
# This gives true parallelism for API calls while keeping budget accounting correct.

# CRITICAL: stage_normalise.py STAGE_GRAPH order matters for efficiency:
# resolve_company FIRST (biggest filter ~30%), then resolve_title, then resolve_location.
# Each subsequent module works on a smaller set.

# CRITICAL: resolve_location pre-filter uses profile["locations"] from context —
# build profile_city_set inside main() from context["profile"], NOT as a module-level
# constant (each profile may differ).

# CRITICAL: sli_observe() called ONCE on ALL rows at the end of main(), not mid-loop.

# CRITICAL: "N Locations" placeholder in scraped.location → always check
# page.structured_job.locations first before scraped.location.

# GOTCHA: scraped.company is often wrong. Priority: structured_job.company > scraped.company.

# GOTCHA: title_tag format "Job Title | Company Name" → split on "|" and take part[0].

# GOTCHA: profile title words with trailing "s" match jobs without it
# ("Engineers" → "Engineer"). Singularize BOTH sides before comparing.

# GOTCHA: visible_text is empty in the ENTIRE dataset. Do not use it.

# GOTCHA: For company pre-filter, strip legal suffixes BEFORE building token set,
# otherwise "Ltd" and "Group" appear in every profile token set and match everything.

# GOTCHA: ThreadPoolExecutor workers share memory — context dict is read-only
# in workers (do not mutate context; each worker gets its own row copies).

# GOTCHA: httpx is available as a transitive dep of anthropic==1.13.0. No new dep needed.
```

---

## Implementation Blueprint

### Data models

```python
# All data flows as plain dict. Key fields set by each module:

# After resolve_title (transform + soft filter):
row["resolved_title"] = str       # best title from priority chain

# After resolve_company (transform + soft filter):
row["resolved_company"] = str     # best company from priority chain

# After resolve_location (collect + soft filter):
row["location_strings"] = list[str]  # ALL raw location strings from all sources
row["is_remote_hint"] = bool         # True if any source contains remote keywords

# After match_jobs (agent, exact match + LLM):
row["matched_company"]   = str
row["matched_job_title"] = list[str]
row["matched_location"]  = list[str]
row["reason"]            = str
row["used_llm"]          = bool
```

### Task list (in order)

---

#### Task 0 — Add Jev + threading.Lock to llm.py

```
MODIFY v2/shared/api_calls/llm.py:
  1. READ https://vercel.com/ai-gateway/models/jev and https://vercel.com/docs/ai-gateway
     to get: exact base URL, Jev model ID, USD/M token pricing

  2. ADD module-level lock:
       import threading
       _budget_lock = threading.Lock()

  3. Wrap budget check + log write with _budget_lock in _call():
       with _budget_lock:
           total = _guard(name, prompt, max_tokens)   # check budget
       text, p_tok, c_tok, stop = _send(...)           # API call (OUTSIDE lock)
       with _budget_lock:
           _write_log(...)                             # write result

  4. ADD to PROVIDERS dict:
       "jev": {
           "key": "VERCEL_API_KEY",
           "base_url": "https://ai-gateway.vercel.sh/v1",  # verify from docs
           "model": "jev",           # verify exact model ID
           "in": <price>,            # from docs, USD per M tokens
           "out": <price>,
       }

  5. ADD _send branch for "jev" using httpx (no new dep):
       POST {base_url}/chat/completions
       Bearer auth with VERCEL_API_KEY
       JSON body: model, messages, max_tokens, temperature=0.0
       Optional: response_format for JSON schema

  6. UPDATE provider(): check VERCEL_API_KEY after Anthropic, before Gemini

  7. ADD to .env.example: VERCEL_API_KEY=your-key-here
```

Pseudocode:

```python
import threading
_budget_lock = threading.Lock()

def _call(prompt, max_tokens, purpose, schema):
    name = provider()
    with _budget_lock:
        total = _guard(name, prompt, max_tokens)   # raises BudgetExceeded if over limit
    started = time.time()
    text, p_tok, c_tok, stop = _send(name, prompt, max_tokens, schema)  # outside lock
    cost = cost_gbp(name, p_tok, c_tok)
    with _budget_lock:
        _append_log(...)   # write to llm_calls.jsonl
    return text.strip()

# Jev _send branch:
if name == "jev":
    import httpx
    spec = PROVIDERS["jev"]
    payload = {"model": spec["model"], "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 0.0}
    if schema:
        payload["response_format"] = {"type": "json_schema",
                                       "json_schema": {"schema": schema, "strict": True}}
    r = httpx.post(f"{spec['base_url']}/chat/completions",
                   headers={"Authorization": f"Bearer {os.environ[spec['key']]}"},
                   json=payload, timeout=30.0)
    r.raise_for_status()
    d = r.json()
    c = d["choices"][0]
    u = d.get("usage", {})
    return c["message"]["content"] or "", u.get("prompt_tokens",0), u.get("completion_tokens",0), c.get("finish_reason","")
```

---

#### Task 1 — Replace resolve_title.py (transform + soft pre-filter)

```
REPLACE v2/workers/job_matcher/normalization/resolve_title.py:
  MODULE_TYPE = "filter"
  REJECTION_REASONS = {"TITLE_NOT_IN_PROFILE"}

  main():
    1. Build profile_title_words from context["profile"]["titles"] ONCE:
         all unique singularized lowercase words across all profile titles
         e.g. {"control", "engineer", "electrical", "cnc", "miller", ...}

    2. For each row:
         resolved = _best_title(row)   # priority chain (see below)
         row["resolved_title"] = resolved
         if no word in title_words(resolved) intersects profile_title_words:
             reject(row, "TITLE_NOT_IN_PROFILE")
```

Pseudocode:

```python
def _best_title(row: dict) -> str:
    page = row.get("page") or {}
    sj   = page.get("structured_job") or {}
    if t := (sj.get("title") or "").strip():
        return t
    if tt := (page.get("title_tag") or "").strip():
        for sep in (" | ", " – ", " - "):
            if sep in tt:
                cand = tt.split(sep)[0].strip()
                if len(cand) >= 5 and "job" not in cand.lower():
                    return cand
        if len(tt) >= 5:
            return tt
    if h := (page.get("h1") or "").strip():
        return h
    return row.get("title", "")

def _profile_title_words(profile_titles: list[str]) -> frozenset[str]:
    words: set[str] = set()
    for pt in profile_titles:
        words.update(_singularize(w) for w in re.split(r"[\s\-/|.,&()+]+", pt.lower()) if w)
    return frozenset(words)

# In main(): reject if title_words(resolved_title) ∩ profile_title_words == ∅
```

---

#### Task 2 — Replace resolve_company.py (transform + soft pre-filter)

```
REPLACE v2/workers/job_matcher/normalization/resolve_company.py:
  MODULE_TYPE = "filter"
  REJECTION_REASONS = {"COMPANY_NOT_IN_PROFILE"}

  main():
    1. Build profile_company_tokens from context["profile"]["companies"] ONCE:
         for each company name: normalize (strip legal suffixes, lowercase)
         collect all 2+ char tokens into a flat set
         e.g. "Aire Calder" → {"aire", "calder"}
              "Cobalt Zephyr Holdings" → {"cobalt", "zephyr"}

    2. For each row:
         resolved = _best_company(row)   # structured_job.company > scraped.company
         row["resolved_company"] = resolved
         norm_tokens = set(normalize_company(resolved).split())
         if norm_tokens ∩ profile_company_tokens == ∅:
             reject(row, "COMPANY_NOT_IN_PROFILE")
```

Pseudocode:

```python
def _best_company(row: dict) -> str:
    page = row.get("page") or {}
    sj   = page.get("structured_job") or {}
    return (sj.get("company") or row.get("company", "")).strip()

def _profile_company_tokens(companies: list[dict]) -> frozenset[str]:
    tokens: set[str] = set()
    for c in companies:
        for tok in normalize_company(c["name"]).split():
            if len(tok) >= 3:  # skip "co", "uk", short noise
                tokens.add(tok)
    return frozenset(tokens)
# normalize_company: strip legal suffixes, lowercase, remove punctuation
# → defined in agent/company_matcher.py, imported here
```

---

#### Task 3 — Replace resolve_location.py (collect + soft pre-filter)

```
REPLACE v2/workers/job_matcher/normalization/resolve_location.py:
  MODULE_TYPE = "filter"
  REJECTION_REASONS = {"LOCATION_NOT_IN_PROFILE"}

  This module does NOT parse cities (that's the LLM's job in stage_agent).
  It only:
    1. Collects all raw location strings from structured_job.locations + scraped.location
       (skips "N Locations" placeholders from scraped, keeps them if in structured_job)
    2. Detects remote keywords (sets is_remote_hint)
    3. Soft pre-filter: rejects rows with NO profile city token AND no remote hints

  main():
    1. Build profile_city_set from context["profile"]["locations"] ONCE:
         all names + all includes values, lowercase
         e.g. {"warrington", "runcorn", "knutsford", "birmingham", "manchester",
               "bolton", "remote", "home-based", "work from home", ...}

    2. For each row:
         strings = _collect_location_strings(row)   # all sources
         row["location_strings"] = strings
         row["is_remote_hint"] = any(remote keyword in s for s in strings)
         if not strings and not row["is_remote_hint"]:
             reject(row, "LOCATION_NOT_IN_PROFILE")
             continue
         # Soft match: any token from any string in profile_city_set?
         tokens = {tok.lower() for s in strings for tok in re.split(r"[\s,/\-|]+", s) if len(tok) >= 3}
         if not (tokens & profile_city_set) and not row["is_remote_hint"]:
             reject(row, "LOCATION_NOT_IN_PROFILE")
```

Pseudocode:

```python
PLACEHOLDER_RE = re.compile(r"^\d+\s+location", re.IGNORECASE)
REMOTE_RE = re.compile(r"\b(remote|home.based|work from home|wfh)\b", re.IGNORECASE)

def _collect_location_strings(row: dict) -> list[str]:
    strings: list[str] = []
    page = row.get("page") or {}
    sj   = page.get("structured_job") or {}
    # structured_job.locations first (more reliable)
    for loc in sj.get("locations") or []:
        if loc and loc.strip():
            strings.append(loc.strip())
    # scraped.location (skip placeholder)
    loc = (row.get("location") or "").strip()
    if loc and not PLACEHOLDER_RE.match(loc):
        strings.append(loc)
    return strings

def _build_profile_city_set(profile_locations: list[dict]) -> frozenset[str]:
    cities: set[str] = set()
    for loc in profile_locations:
        cities.add(loc["name"].lower())
        for inc in loc.get("includes") or []:
            cities.add(inc.lower())
    return frozenset(cities)
```

---

#### Task 4 — Update stage_normalise.py order

```
MODIFY v2/workers/job_matcher/stages/stage_normalise.py:
  Reorder STAGE_GRAPH for maximum early filtering:
    1. filter_dead_links    (remove 404/410 first — cheapest)
    2. filter_duplicates    (dedup by job_id)
    3. resolve_company      (biggest filter: ~30% of jobs don't match any profile company)
    4. resolve_title        (filter: ~40% of remaining don't match any profile title word)
    5. resolve_location     (filter: most of remaining outside profile geographies)
```

---

#### Task 5 — Create company_matcher.py

```
CREATE v2/workers/job_matcher/agent/company_matcher.py:
  - normalize_company(name) → strip legal suffixes, lowercase, remove punctuation
  - build_profile_lookup(companies) → {normalized → original}
  - match_company(resolved, lookup) → original name or None
      1. Exact normalized match
      2. Subset: profile_norm ⊂ company_norm or vice versa
         (handles "Cobalt Zephyr" vs "Cobalt Zephyr Holdings")
```

Legal suffix list: `ltd, limited, plc, group, holdings, international, uk, engineering,
services, solutions, systems, technologies, technology, co, inc, gmbh, llc, company,
industries, manufacturing, the`

---

#### Task 6 — Create title_matcher.py

```
CREATE v2/workers/job_matcher/agent/title_matcher.py:
  - title_words(title) → frozenset[str]
      lowercase, split on /[\s\-/|.,&()+]+/, singularize (rstrip "s" if len>3)
  - matched_titles(job_title, profile_titles) → list[str]
      return profile titles where ALL words ⊆ job title words
      return original strings spelled exactly as in profile file
```

---

#### Task 7 — Create location_matcher.py

```
CREATE v2/workers/job_matcher/agent/location_matcher.py:
  - towns_covered(loc) → frozenset[str] (lowercase: name + includes)
  - matched_locations(resolved_cities, is_remote, country, profile_locations) → list[str]
      For each profile location:
        skip if country mismatch
        type==remote: include if is_remote
        else: include if any resolved_city (lowercase) ∈ towns_covered(loc)
      Return original location name strings
```

---

#### Task 8 — Create match_jobs.py (stage_agent module — the core)

```
CREATE v2/workers/job_matcher/agent/match_jobs.py:
  MODULE_NAME = "job_matcher__match_jobs"
  MODULE_TYPE = "filter"
  REJECTION_REASONS = {"COMPANY_NOT_LISTED", "NO_TITLE_MATCH", "NO_LOCATION_MATCH"}

  main(context, prev_data):
    # prev_data is already small (passed all pre-filters)
    profile = context["profile"]
    company_lookup = build_profile_lookup(profile["companies"])  # once

    # Step 1: exact company + title match (pure code, fast)
    candidates = []
    for row in prev_data:
        mc = match_company(row["resolved_company"], company_lookup)
        if not mc:
            reject(row, "COMPANY_NOT_LISTED"); continue
        mt = matched_titles(row["resolved_title"], profile["titles"])
        if not mt:
            reject(row, "NO_TITLE_MATCH"); continue
        row["_mc"] = mc
        row["_mt"] = mt
        candidates.append(row)

    # Step 2: LLM batch for location extraction (one call for all unique strings)
    if candidates:
        unique_strings = list({s for r in candidates for s in r.get("location_strings", [])})
        city_map = _jev_extract_cities(unique_strings, context["trace_id"])
        # city_map: {"Birmingham, United Kingdom": "Birmingham", "Knutsford, Radbroke Hall": "Knutsford", ...}

    # Step 3: exact location match (pure code)
    for row in candidates:
        resolved_cities = _resolve_cities(row["location_strings"], city_map)
        ml = matched_locations(
            resolved_cities,
            row.get("is_remote_hint", False),
            "United Kingdom",
            profile["locations"],
        )
        if not ml:
            reject(row, "NO_LOCATION_MATCH"); continue
        row["matched_company"]   = row.pop("_mc")
        row["matched_job_title"] = row.pop("_mt")
        row["matched_location"]  = ml
        row["reason"] = f"{row['resolved_title']} at {row['matched_company']} in {', '.join(resolved_cities or ['Remote'])}"
        row["used_llm"] = bool(unique_strings)
```

Pseudocode for `_jev_extract_cities`:

```python
def _jev_extract_cities(location_strings: list[str], trace_id: str) -> dict[str, str]:
    """One LLM call → {raw_string: city_name or ""}."""
    if not location_strings:
        return {}

    schema = {
        "type": "object",
        "properties": {
            "cities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "One city name per input string, empty string if none found"
            }
        },
        "required": ["cities"],
        "additionalProperties": False,
    }
    prompt = (
        "Extract the primary UK city or town name from each location string below. "
        "Return exactly one city name per string (just the city, no country/county). "
        "Return empty string if no city can be identified.\n\n"
        + "\n".join(f"{i+1}. {s}" for i, s in enumerate(location_strings))
    )
    result = ask_json(prompt, schema=schema, purpose="location_extraction")
    cities = result.get("cities", [])
    return {s: cities[i].strip() if i < len(cities) else "" for i, s in enumerate(location_strings)}
```

---

#### Task 9 — Update stage_agent.py

```
MODIFY v2/workers/job_matcher/stages/stage_agent.py:
  ADD to STAGE_GRAPH:
    "match_jobs": StageDefinition(
        name="match_jobs",
        module_path="v2.workers.job_matcher.agent.match_jobs",
    )
```

---

#### Task 10 — Create chunk_runner.py + update handler.py

```
CREATE v2/workers/job_matcher/chunk_runner.py:
  - process_chunk(chunk, context) → list[dict]
      runs stage_normalise → stage_agent on one chunk
      returns only matched rows (have matched_company set)

  - run_chunks(all_rows, context, chunk_size) -> list[dict]
      split all_rows into ceil(len/chunk_size) chunks
      ThreadPoolExecutor(max_workers=min(16, os.cpu_count()*2 or 8))
      submit all chunks, collect results
      return merged matched rows
```

Pseudocode:

```python
import math, os, importlib
from concurrent.futures import ThreadPoolExecutor, as_completed

def process_chunk(chunk: list[dict], context: dict) -> list[dict]:
    stage_normalise = importlib.import_module("v2.workers.job_matcher.stages.stage_normalise")
    stage_agent     = importlib.import_module("v2.workers.job_matcher.stages.stage_agent")
    r = stage_normalise.main(context, chunk)
    r = stage_agent.main(context, r.data)
    return r.data

def run_chunks(all_rows: list[dict], context: dict, chunk_size: int = 1000) -> list[dict]:
    n = max(1, math.ceil(len(all_rows) / chunk_size))
    chunks = [all_rows[i*chunk_size:(i+1)*chunk_size] for i in range(n)]
    workers = min(16, (os.cpu_count() or 4) * 2)

    matched: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_chunk, c, context): i for i, c in enumerate(chunks)}
        for f in as_completed(futures):
            matched.extend(f.result())
    return matched
```

```
MODIFY v2/workers/job_matcher/handler.py:
  ADD CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
  In run_pipeline (or override), after load_job_feed:
    - call run_chunks(loaded_rows, context, CHUNK_SIZE)
    - pass matched rows to stage_output
  ADD stage_report to STAGE_GRAPH
```

---

#### Task 11 — Create generate_report.py + stage_report.py

```
CREATE v2/workers/job_matcher/report/generate_report.py:
  Read runs/<trace_id>/sli_events.jsonl → funnel counts per module
  Read runs/<trace_id>/llm_calls.jsonl → total spend
  Write runs/<trace_id>/report.md:

  ## Run Summary
  Trace: <trace_id> | Profile: <profile_id> | Date: <date>

  ## Pipeline Funnel
  | Module | In | Out | Rejected | Reason |

  ## Matched Jobs (<N> total)
  | job_id | Company | Title(s) | Location(s) |

  ## LLM Usage
  | Calls | Tokens in | Tokens out | Cost GBP |

CREATE v2/workers/job_matcher/stages/stage_report.py:
  Wraps generate_report in stage_loop pattern
```

---

#### Task 12 — Write tests

```
CREATE tests/v2/conftest.py:
  - ctx fixture: {"trace_id": "test", "profile": load_profile_a(), ...}
  - make_row(title, company, location, page={}) helper

CREATE tests/v2/test_resolve_company.py:
  - test_passes_when_token_matches — "Aire Calder Ltd" → in profile (token "aire")
  - test_rejects_amazon — "Amazon" not in profile → rejected
  - test_structured_job_company_preferred — sj.company != scraped.company → uses sj
  - test_legal_suffix_not_in_token_set — "Holdings" alone doesn't match

CREATE tests/v2/test_resolve_title.py:
  - test_passes_engineer_word — "Senior Controls Engineer" → passes (engineer in profile words)
  - test_rejects_accountant — "Senior Accountant" → rejected
  - test_structured_job_title_preferred — sj.title used over scraped
  - test_title_tag_split_on_pipe — "Controls Engineer | Aire Calder" → "Controls Engineer"

CREATE tests/v2/test_resolve_location.py:
  - test_passes_profile_city_token — "Birmingham, UK" → "birmingham" in profile_city_set → pass
  - test_passes_structured_job_location — sj.locations=["Manchester"] → pass
  - test_rejects_london — "London" not in profile_city_set → rejected
  - test_passes_remote_keyword — "Remote - UK" → is_remote_hint=True → pass
  - test_placeholder_skipped_in_scraped — scraped="2 Locations", sj=[] → rejected
  - test_placeholder_uses_structured — scraped="2 Locations", sj=["Warrington"] → pass

CREATE tests/v2/test_title_matcher.py:
  - test_case_insensitive — "controls engineer" matches "Controls Engineer"
  - test_word_order_independent — "Engineer - Electrical" matches "Electrical Engineer"
  - test_non_adjacent — "Quality and Warranty Engineer" matches "Quality Engineer"
  - test_plural_stripped — "Engineers" matches "Engineer"
  - test_no_match — "Software Developer"
  - test_multiple_matches — returns all matched profile titles

CREATE tests/v2/test_company_matcher.py:
  - test_exact_normalized — "Aire Calder" matches
  - test_suffix_stripped — "Cobalt Zephyr Holdings" matches "Cobalt Zephyr"
  - test_the_prefix_stripped — "The Aire Calder" matches "Aire Calder"
  - test_case_insensitive
  - test_no_match — "Amazon"

CREATE tests/v2/test_labelled_sample.py:
  - test_v2_recall_above_80_percent
      Load data/labelled_sample.jsonl (11 YES, 49 NO)
      Run: stage_clean_jobs → run_chunks (chunk_size=100, workers=1 for test)
      Assert: ≥ 9 of 11 YES jobs in output
      Assert: ≤ 5 false positives
```

---

### Integration Points

```yaml
ENV_VARS:
  VERCEL_API_KEY: Jev provider key
  CHUNK_SIZE: int, default 1000 (tune for memory vs parallelism)
  ANTHROPIC_SENIOR_DEVELOPER_KEY: existing (takes priority over Jev)
  GEMINI_SENIOR_DEVELOPER_KEY: existing
  ILLUMINI_RUNS_DIR: existing

STAGE ORDER (handler.py):
  1. stage_clean_jobs  → load_job_feed (serial, I/O)
  2. chunk_runner      → N chunks × ThreadPoolExecutor:
       stage_normalise → resolve_company → resolve_title → resolve_location
       stage_agent     → match_jobs (code + LLM batch per chunk)
  3. stage_output      → generate_output (serial, merge + write)
  4. stage_report      → generate_report (serial)
```

---

## Validation Gates

### Level 1 — Syntax

```bash
.venv/bin/python -m ruff check v2/ tests/v2/ --fix
# Expected: 0 errors
```

### Level 2 — Unit tests

```bash
.venv/bin/python -m pytest tests/v2/ -v -k "not labelled_sample"
# Expected: all pass
```

### Level 3 — Regression (must never break)

```bash
.venv/bin/python -m pytest tests/test_golden.py -v
# Expected: PASS
```

### Level 4 — Integration recall

```bash
.venv/bin/python -m pytest tests/v2/test_labelled_sample.py -v
# Expected: recall ≥ 9/11

# Debug dropped jobs:
cat runs/*/sli_events.jsonl | python -c "
import json, sys
from collections import Counter
evts = [json.loads(l) for l in sys.stdin if l.strip()]
print(Counter((e['META_MODULE'], e.get('META_REJECTION_REASON')) for e in evts if e['META_OUTCOME']=='rejected'))
"
```

### Level 5 — End-to-end smoke

```bash
make run-v2
cat runs/*/report.md
head -3 runs/*/profile_a_matched.jsonl | python -c "
import json,sys
for l in sys.stdin:
    j=json.loads(l)
    assert isinstance(j['matched_job_title'],list) and isinstance(j['matched_location'],list)
print('OK')
"
```

### Level 6 — Scale (200k, < 20 min)

```bash
.venv/bin/python tools/make_scale_feed.py
time CHUNK_SIZE=1000 make run-v2
```

---

## Final Validation Checklist

- [ ] `make test` passes (golden + v1 + v2 unit tests)
- [ ] `ruff check v2/` 0 errors
- [ ] recall ≥ 9/11 in `test_labelled_sample.py`
- [ ] `runs/*/report.md` generated with funnel + matched jobs table
- [ ] `matched_job_title` spelled exactly as in `job_title_searches.json`
- [ ] `matched_location` spelled exactly as in `location_searches.json`
- [ ] No duplicate job_ids in output
- [ ] 200k run completes < 20 min
- [ ] `threading.Lock` wraps budget file read+write, NOT the API call

---

## Anti-Patterns to Avoid

- ❌ Don't hardcode a TOWNS dict — build city set from `context["profile"]["locations"]`
- ❌ Don't reject at normalize if location is empty — check structured_job.locations first
- ❌ Don't put the threading.Lock around the API call — only around file read/write
- ❌ Don't use visible_text — empty in entire dataset
- ❌ Don't use substring containment for titles — use word-set subset
- ❌ Don't do exact string equality for companies — normalize both sides
- ❌ Don't dedup by title|company — use job_id
- ❌ Don't build profile lookups inside per-row loops — build once per main() call
- ❌ Don't forget sli_observe() on ALL rows (passed + rejected) at end of main()
- ❌ Don't hardcode profile_a — always read from context["profile"]

---

## Confidence Score

**9/10** — Full architecture grounded in:
- All v1 bugs documented in NOTES.md
- Exact profile data (408 companies, 57 titles, 12 locations with includes)
- Concrete feed data (location formats, fill rates, empty visible_text)
- ThreadPoolExecutor + threading.Lock pattern is well-understood Python
- One open item: Jev exact model ID + pricing (verify from https://vercel.com/ai-gateway/models/jev)
