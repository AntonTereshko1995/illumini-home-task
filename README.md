# Illumini — Senior Engineer Take-Home

## Docs

- **[NOTES.md](NOTES.md)** — raw notes taken during research: ideas explored, dead ends, observations while reading the codebase and experimenting with approaches.
- **[DECISIONS.md](DECISIONS.md)** — final write-up: thoughts on the problem, decisions made, and solution walkthrough. Written at the end after the implementation was complete.

---

## Setup

```bash
cp .env.example .env   # paste your keys
make dev               # create venv, install deps, install pre-commit hooks
```

### API keys (`.env`)

| Variable                           | Required for                                           |
| ---------------------------------- | ------------------------------------------------------ |
| `AI_GATEWAY_API_KEY`             | JEV via Vercel AI Gateway — **required for v2** |
| `ANTHROPIC_SENIOR_DEVELOPER_KEY` | Anthropic LLM fallback (v1)                            |
| `GEMINI_SENIOR_DEVELOPER_KEY`    | Gemini LLM fallback (v1)                               |

---

## Running

```bash
make run-v2   # run v2 pipeline on the real feed (~200k items)
make run      # run v1 pipeline (baseline, intentionally broken)
```

Output is written to `runs/<timestamp>/`:

- `profile_a_matched.jsonl` — matched jobs
- `sli_events.jsonl` — per-row outcomes for every module
- `llm_calls.jsonl` — every JEV call with tokens and GBP cost
- `llm_prompts.jsonl` — full state + questions + answers per call

```bash
# Debug mode — stops each module after 5 rows
DEBUG_MODE=true make run-v2

# Scale feed — generates 200k items from the 1.5k raw feed
.venv/bin/python tools/make_scale_feed.py
```

---

## Tests

### Without LLM (no API key needed)

```bash
# Full suite — LLM tests auto-skipped if AI_GATEWAY_API_KEY is not set
make test

# v2 normalization pipeline (filter_dead_links, filter_duplicates, resolve_*, full pipeline)
.venv/bin/python -m pytest tests/v2/normalizations/ -v

# v2 match_jobs unit tests (country detection, title filtering, question building, mocked JEV)
.venv/bin/python -m pytest tests/v2/test_match_jobs.py -v

# LLM budget hard-stop (mocked — no real calls made)
.venv/bin/python -m pytest tests/test_llm_cap.py -v

# Golden tests — must always pass
.venv/bin/python -m pytest tests/test_golden.py -v
```

### With LLM (requires `AI_GATEWAY_API_KEY`)

Run the full v2 pipeline against the 300-job labelled dataset and print classification metrics.

```bash
# All LLM tests: recall, precision, f1, output field validation
.venv/bin/python -m pytest tests/v2/test_labelled_sample.py -v -s

# Metrics only — prints classification report
.venv/bin/python -m pytest tests/v2/test_labelled_sample.py::test_classification_metrics -v -s

# Recall check — at least 17/17 YES jobs must be matched
.venv/bin/python -m pytest tests/v2/test_labelled_sample.py::test_recall_meets_target_threshold -v -s

# False positive check — no labelled NO jobs in the output
.venv/bin/python -m pytest tests/v2/test_labelled_sample.py::test_no_false_positives -v -s
```

Expected output from `test_classification_metrics`:
```
--- Classification report ---
              precision    recall  f1-score   support

          no       0.98      1.00      0.99       283
         yes       0.91      0.59      0.71        17

    accuracy                           0.97       300
```

---

## Key constants

| Constant                 | Location                                       | Default                    | Override via                |
| ------------------------ | ---------------------------------------------- | -------------------------- | --------------------------- |
| `BUDGET_GBP`           | `v2/shared/api_calls/llm.py`                 | `£3.00`                 | hardcoded                   |
| `_MODEL_ID`            | `v2/shared/api_calls/llm.py`                 | `typesafe-ai/jev`        | hardcoded                   |
| `_DEFAULT_CHUNK_SIZE`  | `v2/workers/job_matcher/chunk_runner.py`     | `500` items              | `CHUNK_SIZE` env var      |
| `_DEFAULT_CONCURRENCY` | `v2/workers/job_matcher/chunk_runner.py`     | `500` batches            | `LLM_CONCURRENCY` env var |
| `_CONCURRENCY`         | `v2/workers/job_matcher/agent/match_jobs.py` | `10` JEV calls per chunk | hardcoded                   |

> **Rate limit note:** 500 concurrent batches triggers DigitalOcean's 3000 req/min limit. Set `LLM_CONCURRENCY=300` to stay within it.

```bash
LLM_CONCURRENCY=300 make run-v2
```
