# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make dev          # create venv, install deps (incl. dev), install pre-commit hooks
make run          # run the job_matcher on the real feed; writes runs/<timestamp>/profile_a_matched.jsonl
make test         # run the full pytest suite (golden + llm_cap tests)

# Single test
.venv/bin/python -m pytest tests/test_golden.py -q

# Debug mode (stops each module after 5 rows)
DEBUG_MODE=true make run

# Scale feed (200k jobs from the 1.5k raw)
.venv/bin/python tools/make_scale_feed.py
```

The `.env` file must have `ANTHROPIC_SENIOR_DEVELOPER_KEY` or `GEMINI_SENIOR_DEVELOPER_KEY`. Copy `.env.example` to `.env`.

## Architecture

This is a **two-stage pipeline** with a strict module contract. The entry point is `v1/workers/job_matcher/handler.py`, which defines a `STAGE_GRAPH` of two stages:

1. **`stage_clean_jobs`** — load, normalise, dedup, and resolve the raw job feed to a canonical shape
2. **`stage_match_jobs`** — filter jobs against one recruiter profile; write the output file

Each stage itself has a `STAGE_GRAPH` of **modules** run in order. The data flows: `handler → stage → module → module → ...` Each step receives `context` (a dict with the run's metadata/profile) and `prev_data` (list of row dicts), and returns an `ExecutionResult`. Stages are in `stages/`, modules are in `modules/`.

### Module contract (must be followed for all new/changed modules)

- Top-level constants: `MODULE_NAME`, `MODULE_TYPE` (`transform`/`filter`/`explode`), `REJECTION_REASONS`, `ERROR_REASONS`, `WARNING_REASONS`
- `main(context, prev_data) -> ExecutionResult`
- Tag each row with `reject(row, "REASON")` from `sli_observe`; call `sli_observe(rows, ...)` **once** at the end on **all** rows (not just kept ones)
- Return `ExecutionResult(..., data=kept)` where `kept = passed(rows)`
- No `print()`. Use `log_event(logger, ...)` from `v1/shared/patterns/logging.py`

### Observability

Every run writes to `runs/<trace_id>/`:
- `profile_<id>_matched.jsonl` — the output (one JSON line per matched job)
- `sli_events.jsonl` — one event per row per module (outcome, rejection reason); use this to diagnose where rows are dropped
- `llm_calls.jsonl` — every LLM call with tokens and GBP cost

### LLM usage

`v1/shared/api_calls/llm.py` is the **only** way to call an LLM. Use `ask(prompt, purpose=...)` for text or `ask_json(prompt, schema=..., purpose=...)` for structured output. Budget: £1 target, £3.00 hard stop (`BudgetExceeded` raised before sending). Provider: Anthropic if its key is set, else Gemini.

## Matching rules (from OUTPUT_FORMAT.json)

A job is included when **all three** pass:

| Signal | Rule |
|--------|------|
| **Company** | Company name appears anywhere on the page (declared fields, title tag, URL, body text). Match ignores case, punctuation, a leading "The", and legal suffixes (Ltd, plc, Group, Holdings, International, UK). |
| **Title** | Every word of the profile title appears in the job's title in any order, case/punctuation-insensitive, ignoring a trailing plural *s*. |
| **Location** | A `city` covers itself + its `includes`. A `sub_region` covers itself + any town inside it. A `remote` location covers jobs the employer declares remote/home-based in that country. Multiple locations on a job: match if **any** matches. Jobs in a different country never match. |
| **Live** | HTTP status 404 or 410 → out. |

`matched_job_title` and `matched_location` list **every** profile entry that matched (not just the first).

## Known bugs in v1 (deliberately broken)

- `resolve_job_town` does only exact-string lookup against a small hardcoded UK TOWNS dict — most jobs fail as `UNKNOWN_LOCATION`. Location extraction should look at multiple page fields and handle multi-location strings.
- `matched_titles` in `match_jobs.py` uses substring containment (`t in job_title`) — the actual rule is every word of the profile title must appear in the job title.
- `matched_locations` passes bare town name to `towns_covered` but profile location `includes` is a list of strings — the towns_covered logic itself is correct, but the job's resolved `town` may not align with what profiles list.
- Company matching is exact string equality against `scraped.company` only — the real rule requires fuzzy matching across multiple page signals.

## Data

- `data/jobs_raw.jsonl` — ~1,500 raw jobs; each has `job_id`, `scraped` (title/company/location/salary), `source_url`, `page` (http_status, title_tag, h1, meta, visible_text, structured_job)
- `data/user_search_inputs/profile_a/` — the recruiter profile (company_searches.json, job_title_searches.json, location_searches.json)
- `data/labelled_sample.jsonl` — 60 hand-labelled jobs; the only ground truth available locally
- `data/golden/` — tiny fixture used by the golden test; must keep passing
