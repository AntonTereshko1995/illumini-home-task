"""The shared worker runtime: the local stand-in for Illumini's streaming runtime.

In production, one SQS message = one user = one trace, and the runtime receives it, validates the context, runs
the handler's STAGE_GRAPH and sends the result on. Here, one profile file = one "message": run_pipeline builds
its context, validates it against the handler's INPUT_CONTEXT_SCHEMA, runs every stage in STAGE_GRAPH order and
validates the result against OUTPUT_CONTEXT_SCHEMA. Handlers, stages and modules never do this plumbing.

    handler.py   HANDLER_NAME + schemas + STAGE_GRAPH of stages        -> run_local_handler / run_pipeline
    stages/*.py  STAGE_NAME + STAGE_GRAPH of modules + inline schemas   -> run_stage_loop
    modules/*.py main(context, prev_data) -> ExecutionResult             (the logic lives here)
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v2.shared.api_calls import llm
from v2.shared.patterns.logging import get_logger, log_event

DEFAULT_JOBS = Path("data/jobs_raw.jsonl")
DEFAULT_SEARCH_INPUTS = Path("data/user_search_inputs")
SEARCH_INPUT_FILES = {"companies": "company_searches.json", "titles": "job_title_searches.json",
                      "locations": "location_searches.json"}  # fmt: skip


@dataclass
class ExecutionResult:
    """What every module and stage returns: the rows for the next step, plus named artifacts (e.g. a file path)."""

    trace_id: str
    script_span_id: str
    data: list[dict]
    artifacts: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageDefinition:
    """One node of a STAGE_GRAPH: a stage (in a handler) or a module (in a stage), by dotted module path."""

    name: str
    module_path: str


def new_trace_id() -> str:
    """Run timestamp, also the run's folder name under runs/."""
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"


def run_dir(trace_id: str) -> Path:
    """runs/<trace_id>/ (ILLUMINI_RUNS_DIR overrides runs/), created on first use."""
    path = Path(os.environ.get("ILLUMINI_RUNS_DIR", "runs")) / trace_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def debug_limits() -> tuple[bool, int]:
    """(DEBUG_MODE, DEBUG_LOOPS) from the environment: big loops stop after DEBUG_LOOPS rows in debug mode."""
    return os.environ.get("DEBUG_MODE", "false").lower() == "true", int(os.environ.get("DEBUG_LOOPS", "5"))


def validate_context(context: dict, schema: dict) -> None:
    """Raise ValueError when a non-nullable field is missing or a field has the wrong type."""
    for name, spec in schema["fields"].items():
        value = context.get(name)
        if value is None:
            if not spec["nullable"]:
                raise ValueError(f"context schema {schema['version']}: {name!r} is required")
        elif not isinstance(value, spec["type"]):
            raise ValueError(f"context schema {schema['version']}: {name!r} must be {spec['type'].__name__}")


def run_stage_loop(
    stage_name: str, stage_graph: dict[str, StageDefinition], context: dict, prev_data: list[dict]
) -> ExecutionResult:
    """Run each module in STAGE_GRAPH order, feeding each one the previous module's data."""
    data, artifacts = prev_data, {}
    for node in stage_graph.values():
        result = importlib.import_module(node.module_path).main(context, data)
        data = result.data
        artifacts.update(result.artifacts)
    return ExecutionResult(
        trace_id=context["trace_id"],
        script_span_id=f"{stage_name}_{context['trace_id']}",
        data=data,
        artifacts=artifacts,
        metrics={},
    )


def load_search_inputs(root: Path) -> list[tuple[str, dict]]:
    """(output prefix, profile) per recruiter. Each recruiter is a folder of three search files:
    company_searches.json {"profile_id", "companies"}, job_title_searches.json {"profile_id", "titles"} and
    location_searches.json {"profile_id", "locations"}, read back into one profile. A missing file or a
    profile_id that differs between the three raises. A plain <prefix>.json profile (the older layout) still loads."""
    profiles: list[tuple[str, dict]] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        present = {field: folder / name for field, name in SEARCH_INPUT_FILES.items() if (folder / name).exists()}
        if not present:
            continue
        if len(present) != len(SEARCH_INPUT_FILES):
            missing = sorted(set(SEARCH_INPUT_FILES.values()) - {p.name for p in present.values()})
            raise ValueError(f"{folder}: missing search input files {missing}")
        parts = {field: json.loads(path.read_text(encoding="utf-8")) for field, path in present.items()}
        ids = {part["profile_id"] for part in parts.values()}
        if len(ids) != 1:
            raise ValueError(f"{folder}: profile_id differs across the search input files: {sorted(ids)}")
        profiles.append((folder.name, {"profile_id": ids.pop(), **{f: parts[f][f] for f in SEARCH_INPUT_FILES}}))
    for path in sorted(root.glob("*.json")):
        profiles.append((path.stem, json.loads(path.read_text(encoding="utf-8"))))
    return profiles


def run_pipeline(
    stage_graph: dict[str, StageDefinition],
    input_schema: dict,
    output_schema: dict,
    handler_name: str,
    jobs_path: Path,
    search_inputs_dir: Path,
) -> dict[str, str]:
    """One trace per call; one "message" per recruiter in search_inputs_dir. Returns {output file: listed job count}."""
    trace_id = new_trace_id()
    logger = get_logger(handler_name)
    llm.start_run(run_dir(trace_id))
    log_event(logger, "info", "run_started", trace_id, jobs_path=str(jobs_path),
              search_inputs_dir=str(search_inputs_dir))  # fmt: skip
    outputs: dict[str, str] = {}
    for prefix, profile in load_search_inputs(Path(search_inputs_dir)):
        context = {
            "trace_id": trace_id,
            "jobs_path": str(jobs_path),
            "profile": profile,
            "profile_id": profile["profile_id"],
            "output_prefix": prefix,
        }
        validate_context(context, input_schema)
        data: list[dict] = []
        for node in stage_graph.values():
            result = importlib.import_module(node.module_path).main(context, data)
            data = result.data
            context.update(result.artifacts)
        validate_context(context, output_schema)
        outputs[context["output_path"]] = str(len(data))
    log_event(logger, "info", "run_finished", trace_id, outputs=outputs, llm_spent_gbp=round(llm.spent_gbp(), 4))
    return outputs


def run_local_handler(
    stage_graph: dict[str, StageDefinition], input_schema: dict, output_schema: dict, handler_name: str
) -> int:
    """Entry point for `python -m <handler module>`: parse --jobs / --search-inputs, run, print one line per output."""
    parser = argparse.ArgumentParser(prog=handler_name)
    parser.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    parser.add_argument("--search-inputs", "--briefs", dest="search_inputs", type=Path, default=DEFAULT_SEARCH_INPUTS)
    args, _ = parser.parse_known_args()
    for path, count in run_pipeline(
        stage_graph, input_schema, output_schema, handler_name, args.jobs, args.search_inputs
    ).items():
        print(f"{count:>5} matches -> {path}")
    return 0
