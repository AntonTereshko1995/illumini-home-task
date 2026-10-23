"""Generate a markdown report for a completed run."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def generate(run_dir: Path, elapsed_seconds: float | None = None) -> Path:
    """Write runs/<trace_id>/report.md; return its path."""
    sli_path = run_dir / "sli_events.jsonl"
    llm_path = run_dir / "llm_calls.jsonl"
    trace_id = run_dir.name

    # --- SLI funnel ---
    module_counts: dict[str, Counter] = defaultdict(Counter)
    if sli_path.exists():
        with sli_path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                e = json.loads(line)
                module_counts[e["META_MODULE"]][e["META_OUTCOME"]] += 1

    # --- Matched jobs ---
    matched_rows: list[dict] = []
    for jsonl_path in sorted(run_dir.glob("*_matched.jsonl")):
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    matched_rows.append(json.loads(line))

    # --- LLM spend ---
    total_cost = 0.0
    llm_calls = 0
    if llm_path.exists():
        with llm_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    total_cost += rec.get("cost_gbp", 0.0)
                    llm_calls += 1

    # --- Build report ---
    elapsed_str = f"{elapsed_seconds:.1f}s" if elapsed_seconds is not None else "n/a"
    lines: list[str] = [
        "# Job Matcher v2 Run Report",
        "",
        f"**Trace ID:** `{trace_id}`  ",
        f"**Pipeline time:** {elapsed_str}  ",
        f"**Matched jobs:** {len(matched_rows)}  ",
        f"**LLM calls:** {llm_calls}  ",
        f"**LLM spend:** £{total_cost:.4f}",
        "",
    ]

    # Funnel table
    if module_counts:
        lines += [
            "## Pipeline Funnel",
            "",
            "| Module | Pass | Rejected | Error |",
            "|--------|-----:|--------:|------:|",
        ]
        for module, counts in sorted(module_counts.items()):
            lines.append(
                f"| `{module}` | {counts.get('pass', 0)} | {counts.get('rejected', 0)} | {counts.get('error', 0)} |"
            )
        lines.append("")

    # Matched jobs table
    if matched_rows:
        lines += [
            "## Matched Jobs",
            "",
            "| Job ID | Company | Title(s) | Location(s) |",
            "|--------|---------|----------|-------------|",
        ]
        for r in matched_rows:
            titles = ", ".join(r.get("matched_job_title") or [])
            locs = ", ".join(r.get("matched_location") or [])
            lines.append(f"| `{r['job_id']}` | {r.get('matched_company', '')} | {titles} | {locs} |")
        lines.append("")
    else:
        lines += ["## Matched Jobs", "", "_No matches._", ""]

    report = run_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report
