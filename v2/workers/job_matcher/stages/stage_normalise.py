from v2.shared.patterns.worker_runtime import StageDefinition, run_stage_loop

STAGE_NAME = "stage_normalise"

STAGE_GRAPH = {
    "filter_dead_links": StageDefinition(
        name="filter_dead_links",
        module_path="v2.workers.job_matcher.normalization.filter_dead_links",
    ),
    "filter_duplicates": StageDefinition(
        name="filter_duplicates",
        module_path="v2.workers.job_matcher.normalization.filter_duplicates",
    ),
    "resolve_company": StageDefinition(
        name="resolve_company",
        module_path="v2.workers.job_matcher.normalization.resolve_company",
    ),
    "resolve_title": StageDefinition(
        name="resolve_title",
        module_path="v2.workers.job_matcher.normalization.resolve_title",
    ),
    "resolve_location": StageDefinition(
        name="resolve_location",
        module_path="v2.workers.job_matcher.normalization.resolve_location",
    ),
}

INPUT_CONTEXT_SCHEMA = {
    "version": "v2.0.0",
    "domain": "context",
    "fields": {
        "trace_id": {"type": str, "nullable": False},
    },
}

OUTPUT_CONTEXT_SCHEMA = {
    "version": "v2.0.0",
    "domain": "context",
    "fields": {
        "trace_id": {"type": str, "nullable": False},
    },
}


def main(context: dict, prev_data: list[dict]):
    return run_stage_loop(STAGE_NAME, STAGE_GRAPH, context, prev_data)
