# job_matcher worker (v1)

This version is deliberately incorrect and error-ridden, run it with `make run`
(`python -m v1.workers.job_matcher.handler [--jobs ...] [--search-inputs ...]`).

The worker framework looks like this:
- `v1/shared` - the global shared code (runtime, logging, `sli_observe`, schemas, `llm.py`)
- `v1/workers` - one folder per worker, these would typically be AWS Fargate workers in production
- `handler.py` - the entry point
- `stages` - the 2 core steps, cleaning the data (`stage_clean_jobs`) then matching it (`stage_match_jobs`)
- `modules` - the python files that each stage runs, in its `STAGE_GRAPH` order
- `_shared` - helpers only this specific worker uses, e.g. `town_lookup.py`

## What a run writes (`runs/<trace_id>/`)

- `profile_<id>_matched.jsonl` - the output
- `sli_events.jsonl` - one fact per row per module (outcome, reason), shows where rows died
- `llm_calls.jsonl` - every LLM call, with its cost and purpose

## Module contract

Follow this for any module you add or change.

Constants at the top: `MODULE_NAME`, `MODULE_TYPE` (transform / filter / explode), `REJECTION_REASONS`,
`ERROR_REASONS` and `WARNING_REASONS`.

`main(context, prev_data)` opens with `trace_id`, `start_time` and `logger`, tags every row
(`reject(row, "REASON")` or leave it "pass"), calls `sli_observe` once at the end on all rows, and returns one
`ExecutionResult`. No `print()`, no row totals in logs.

You may restructure it however you like. In this shape, a new step is a new file in `modules/` plus one
`StageDefinition` in a stage's `STAGE_GRAPH`.
