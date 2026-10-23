"""Write the run report after all matching is complete."""

from __future__ import annotations

from pathlib import Path

from v2.shared.patterns.logging import get_logger, log_event
from v2.shared.patterns.worker_runtime import ExecutionResult
from v2.workers.job_matcher.report.generate_report import generate

STAGE_NAME = "stage_report"


def main(context: dict, prev_data: list[dict]) -> ExecutionResult:
    trace_id: str = context.get("trace_id", "unknown")
    logger = get_logger(STAGE_NAME)
    runs_dir = context.get("runs_dir")
    if runs_dir:
        run_path = Path(runs_dir)
    else:
        from v2.shared.patterns.worker_runtime import run_dir as _run_dir

        run_path = _run_dir(trace_id)

    elapsed: float | None = context.get("elapsed_seconds")
    report_path = generate(run_path, elapsed_seconds=elapsed)
    log_event(logger, "info", "report_written", trace_id, report_path=str(report_path))
    return ExecutionResult(
        trace_id=trace_id,
        script_span_id=f"{STAGE_NAME}_{trace_id}",
        data=prev_data,
        artifacts={"report_path": str(report_path)},
        metrics={},
    )
