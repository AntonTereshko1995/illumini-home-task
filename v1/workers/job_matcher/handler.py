import sys

from v1.shared.patterns.worker_runtime import StageDefinition, run_local_handler
from v1.shared.schemas.job_matcher.v1 import JOB_MATCHER_SCHEMA as OUTPUT_CONTEXT_SCHEMA
from v1.shared.schemas.pipeline_start_takehome.v1 import PIPELINE_START_TAKEHOME_SCHEMA as INPUT_CONTEXT_SCHEMA

HANDLER_NAME = "job_matcher"
VERSION = "v1.0.0"

STAGE_GRAPH = {
    "stage_clean_jobs": StageDefinition(
        name="stage_clean_jobs",
        module_path="v1.workers.job_matcher.stages.stage_clean_jobs",
    ),
    "stage_match_jobs": StageDefinition(
        name="stage_match_jobs",
        module_path="v1.workers.job_matcher.stages.stage_match_jobs",
    ),
}

if __name__ == "__main__":
    sys.exit(run_local_handler(STAGE_GRAPH, INPUT_CONTEXT_SCHEMA, OUTPUT_CONTEXT_SCHEMA, HANDLER_NAME))
