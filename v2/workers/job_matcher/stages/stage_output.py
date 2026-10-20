from v2.shared.patterns.worker_runtime import StageDefinition, run_stage_loop

STAGE_NAME = "stage_output"

STAGE_GRAPH = {
    "generate_output": StageDefinition(
        name="generate_output",
        module_path="v2.workers.job_matcher.modules.generate_output",
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
