import sys

from v2.shared.patterns.worker_runtime import StageDefinition, run_local_handler
from v2.shared.schemas.job_matcher.v1 import JOB_MATCHER_SCHEMA as OUTPUT_CONTEXT_SCHEMA
from v2.shared.schemas.pipeline_start_takehome.v1 import PIPELINE_START_TAKEHOME_SCHEMA as INPUT_CONTEXT_SCHEMA

HANDLER_NAME = "job_matcher"
VERSION = "v2.0.0"

STAGE_GRAPH = {
    "stage_clean_jobs": StageDefinition(
        name="stage_clean_jobs",
        module_path="v2.workers.job_matcher.stages.stage_clean_jobs",
    ),
    "stage_normalise": StageDefinition(
        name="stage_normalise",
        module_path="v2.workers.job_matcher.stages.stage_normalise",
    ),
    "stage_agent": StageDefinition(
        name="stage_agent",
        module_path="v2.workers.job_matcher.stages.stage_agent",
    ),
    "stage_output": StageDefinition(
        name="stage_output",
        module_path="v2.workers.job_matcher.stages.stage_output",
    ),
}

if __name__ == "__main__":
    sys.exit(run_local_handler(STAGE_GRAPH, INPUT_CONTEXT_SCHEMA, OUTPUT_CONTEXT_SCHEMA, HANDLER_NAME))
