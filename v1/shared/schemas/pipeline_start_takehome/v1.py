"""Context schema for the start of the take-home pipeline: what one "message" (one profile) carries in."""

PIPELINE_START_TAKEHOME_SCHEMA = {
    "version": "v1.0.0",
    "domain": "context",
    "fields": {
        "trace_id": {"type": str, "nullable": False},
        "jobs_path": {"type": str, "nullable": False},
        "profile": {"type": dict, "nullable": False},
        "profile_id": {"type": str, "nullable": False},
        "output_prefix": {"type": str, "nullable": False},
    },
}
