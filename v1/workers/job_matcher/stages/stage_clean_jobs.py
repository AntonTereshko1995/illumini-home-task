from v1.shared.patterns.worker_runtime import StageDefinition, run_stage_loop

STAGE_NAME = "stage_clean_jobs"

STAGE_GRAPH = {
    "load_job_feed": StageDefinition(
        name="load_job_feed",
        module_path="v1.workers.job_matcher.modules.load_job_feed",
    ),
    "normalise_job_rows": StageDefinition(
        name="normalise_job_rows",
        module_path="v1.workers.job_matcher.modules.normalise_job_rows",
    ),
    "drop_duplicate_jobs": StageDefinition(
        name="drop_duplicate_jobs",
        module_path="v1.workers.job_matcher.modules.drop_duplicate_jobs",
    ),
    "resolve_job_town": StageDefinition(
        name="resolve_job_town",
        module_path="v1.workers.job_matcher.modules.resolve_job_town",
    ),
}

INPUT_CONTEXT_SCHEMA = {
    "version": "v1.0.0",
    "domain": "context",
    "fields": {
        "trace_id": {"type": str, "nullable": False},
        "jobs_path": {"type": str, "nullable": False},
    },
}

OUTPUT_CONTEXT_SCHEMA = {
    "version": "v1.0.0",
    "domain": "context",
    "fields": {
        "trace_id": {"type": str, "nullable": False},
    },
}


def main(context, prev_data):
    return run_stage_loop(STAGE_NAME, STAGE_GRAPH, context, prev_data)
