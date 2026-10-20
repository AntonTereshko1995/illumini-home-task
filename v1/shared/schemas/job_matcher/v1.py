"""Output context schema of the job_matcher worker: the input fields plus the matches file it wrote."""

from v1.shared.schemas.pipeline_start_takehome.v1 import PIPELINE_START_TAKEHOME_SCHEMA

JOB_MATCHER_SCHEMA = {
    "version": "v1.0.0",
    "domain": "context",
    "fields": {
        **PIPELINE_START_TAKEHOME_SCHEMA["fields"],
        "output_path": {"type": str, "nullable": False},
    },
}
