---
name: project-v2-architecture
description: "v2 job matcher — IMPLEMENTED 2026-10-20; architecture, key decisions, recall results"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f11817d-8fa5-46d8-9325-987aa319da85
---

v2 job matcher FULLY IMPLEMENTED (commit ff43ca4, 2026-10-20).

**Why:** v1 matches 0/11 YES jobs (all fail at crude hardcoded TOWNS dict). v2 uses profile-driven soft pre-filters + fuzzy exact matching.

**Results:** 8/11 recall on labelled sample, 0 false positives. The 3 misses (J576140, J229510 — locations Derby/Bristol not in profile; J809819 — Bromborough not in profile city set) are data-limitation gaps.

**Key architecture decisions:**
- No LLM for matching — pure code (fuzzy token-set matching covers all YES jobs that can be matched)
- Parallelism: ThreadPoolExecutor (not ProcessPool), CHUNK_SIZE env var, default 500
- Location: reads sj.location + sj.additional_locations + sj.locations + scraped.location (skips "N Locations" placeholder)
- Company: strip legal suffixes (incl. "corp"), token-set subset matching
- Title: frozenset word-set, strip trailing "s" on words >3 chars
- filter_dead_links: now rejects 403/405 + pages with completely empty structured data
- threading.Lock in llm.py: wraps budget file read/write only, not API call

**Key files:**
- `v2/workers/job_matcher/agent/company_matcher.py` — normalize + fuzzy match
- `v2/workers/job_matcher/agent/title_matcher.py` — word-set matching
- `v2/workers/job_matcher/agent/location_matcher.py` — profile city coverage
- `v2/workers/job_matcher/agent/match_jobs.py` — MODULE: final 3-signal gate
- `v2/workers/job_matcher/chunk_runner.py` — ThreadPoolExecutor runner
- `v2/workers/job_matcher/handler.py` — parallel pipeline entry point
- `v2/workers/job_matcher/report/generate_report.py` — markdown report
- `tests/v2/` — 56 tests all passing

**How to apply:** Implementation complete. `make run-v2` runs the pipeline; `make test` includes all v2 tests.
