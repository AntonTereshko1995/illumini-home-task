from v2.shared.patterns.worker_runtime import run_stage_loop

STAGE_NAME = "stage_agent"

# Empty — AI matching implementation TBD.
# Agent modules will read resolved_title, resolved_company, town, region, country
# and set: matched_company, matched_job_title, matched_location, reason on matched rows.
STAGE_GRAPH = {}

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
