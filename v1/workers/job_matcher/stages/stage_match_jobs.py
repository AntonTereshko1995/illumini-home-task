from v1.shared.patterns.worker_runtime import StageDefinition, run_stage_loop

STAGE_NAME = "stage_match_jobs"

STAGE_GRAPH = {
    "match_jobs": StageDefinition(
        name="match_jobs",
        module_path="v1.workers.job_matcher.modules.match_jobs",
    ),
    "portal_matches_output": StageDefinition(
        name="portal_matches_output",
        module_path="v1.workers.job_matcher.modules.portal_matches_output",
    ),
}

INPUT_CONTEXT_SCHEMA = {
    "version": "v1.0.0",
    "domain": "context",
    "fields": {
        "trace_id": {"type": str, "nullable": False},
        "profile": {"type": dict, "nullable": False},
        "output_prefix": {"type": str, "nullable": False},
    },
}

OUTPUT_CONTEXT_SCHEMA = {
    "version": "v1.0.0",
    "domain": "context",
    "fields": {
        "output_path": {"type": str, "nullable": False},
    },
}


def main(context, prev_data):
    return run_stage_loop(STAGE_NAME, STAGE_GRAPH, context, prev_data)
