from __future__ import annotations

import json
from pathlib import Path

from tests.v1.helpers import make_row
from v1.workers.job_matcher.modules import portal_matches_output

REQUIRED_FIELDS = {
    "job_id",
    "profile_id",
    "matched_company",
    "matched_job_title",
    "matched_location",
    "reason",
    "used_llm",
}


def make_matched_row(**kwargs) -> dict:
    """Normalised row with all match fields populated."""
    return make_row(
        matched_company="Acme Corp",
        matched_job_title=["Controls Engineer"],
        matched_location=["Warrington"],
        reason="Controls Engineer at Acme Corp, in Warrington",
        used_llm=False,
        **kwargs,
    )


def test_portal_output_file_created(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    assert Path(result.artifacts["output_path"]).exists()


def test_portal_output_file_name(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    assert Path(result.artifacts["output_path"]).name == "profile_test_matched.jsonl"


def test_portal_output_has_required_fields(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    records = [json.loads(line) for line in Path(result.artifacts["output_path"]).read_text().splitlines()]
    assert len(records) == 1
    assert REQUIRED_FIELDS.issubset(records[0].keys())


def test_portal_output_profile_id_from_context(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    record = json.loads(Path(result.artifacts["output_path"]).read_text().splitlines()[0])
    assert record["profile_id"] == "test"


def test_portal_output_empty_input(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [])
    assert Path(result.artifacts["output_path"]).read_text() == ""


def test_portal_used_llm_false_by_default(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    record = json.loads(Path(result.artifacts["output_path"]).read_text().splitlines()[0])
    assert record["used_llm"] is False


def test_portal_output_multiple_rows(ctx, profile, tmp_path):
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    rows = [make_matched_row(job_id="J001"), make_matched_row(job_id="J002")]
    result = portal_matches_output.main(ctx, rows)
    lines = Path(result.artifacts["output_path"]).read_text().splitlines()
    assert len(lines) == 2
    ids = {json.loads(line)["job_id"] for line in lines}
    assert ids == {"J001", "J002"}


def test_portal_output_artifact_key(ctx, profile, tmp_path):
    """artifacts dict must contain 'output_path' key for the pipeline context update."""
    ctx["profile"] = profile
    ctx["output_prefix"] = "profile_test"
    result = portal_matches_output.main(ctx, [make_matched_row()])
    assert "output_path" in result.artifacts
