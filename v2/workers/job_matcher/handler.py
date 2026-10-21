"""v2 job matcher handler — parallel chunked pipeline."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from v2.shared.api_calls import llm
from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import (
    DEFAULT_JOBS,
    DEFAULT_SEARCH_INPUTS,
    load_search_inputs,
    new_trace_id,
    run_dir,
    validate_context,
)
from v2.shared.schemas.job_matcher.v1 import JOB_MATCHER_SCHEMA as OUTPUT_CONTEXT_SCHEMA
from v2.shared.schemas.pipeline_start_takehome.v1 import PIPELINE_START_TAKEHOME_SCHEMA as INPUT_CONTEXT_SCHEMA

HANDLER_NAME = "job_matcher"
VERSION = "v2.0.0"


def run_parallel_pipeline(jobs_path: Path, search_inputs_dir: Path) -> dict[str, str]:
    """Load all jobs once, run parallel normalization+agent per recruiter, then output."""
    trace_id = new_trace_id()
    logger = get_logger(HANDLER_NAME)
    rd = run_dir(trace_id)
    llm.start_run(rd)
    log_event(logger, "info", "run_started", trace_id, jobs_path=str(jobs_path))

    stage_clean_jobs = importlib.import_module("v2.workers.job_matcher.stages.stage_clean_jobs")
    stage_output = importlib.import_module("v2.workers.job_matcher.stages.stage_output")
    stage_report = importlib.import_module("v2.workers.job_matcher.stages.stage_report")
    chunk_runner = importlib.import_module("v2.workers.job_matcher.chunk_runner")

    outputs: dict[str, str] = {}
    for prefix, profile in load_search_inputs(Path(search_inputs_dir)):
        context = {
            "trace_id": trace_id,
            "jobs_path": str(jobs_path),
            "profile": profile,
            "profile_id": profile["profile_id"],
            "output_prefix": prefix,
        }
        validate_context(context, INPUT_CONTEXT_SCHEMA)

        # Stage 1: load
        load_result = stage_clean_jobs.main(context, [])
        all_rows = load_result.data

        # Stages 2+3: normalize + agent in parallel chunks
        matched = chunk_runner.run_chunks(all_rows, context)

        # Stage 4: output
        output_result = stage_output.main(context, matched)
        context.update(output_result.artifacts)

        validate_context(context, OUTPUT_CONTEXT_SCHEMA)
        outputs[context["output_path"]] = str(len(output_result.data))

    # Stage 5: report (per run, after all profiles)
    report_context = {"trace_id": trace_id, "runs_dir": str(rd)}
    stage_report.main(report_context, [])

    log_event(logger, "info", "run_finished", trace_id, outputs=outputs,
              llm_spent_gbp=round(llm.spent_gbp(), 4))  # fmt: skip
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog=HANDLER_NAME)
    parser.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    parser.add_argument("--search-inputs", "--briefs", dest="search_inputs",
                        type=Path, default=DEFAULT_SEARCH_INPUTS)  # fmt: skip
    args, _ = parser.parse_known_args()
    for path, count in run_parallel_pipeline(args.jobs, args.search_inputs).items():
        print(f"{count:>5} matches -> {path}")
    sys.exit(0)
