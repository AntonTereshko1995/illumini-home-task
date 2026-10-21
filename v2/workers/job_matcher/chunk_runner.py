"""Split the job feed into chunks and run normalize+agent on each in parallel."""

from __future__ import annotations

import importlib
import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

_DEFAULT_CHUNK_SIZE = 500
_MAX_WORKERS = min(16, (os.cpu_count() or 4) * 2)


def _process_chunk(chunk: list[dict], context: dict) -> list[dict]:
    stage_normalise = importlib.import_module("v2.workers.job_matcher.stages.stage_normalise")
    stage_agent = importlib.import_module("v2.workers.job_matcher.stages.stage_agent")
    r = stage_normalise.main(context, chunk)
    r = stage_agent.main(context, r.data)
    return r.data


def run_chunks(all_rows: list[dict], context: dict) -> list[dict]:
    """Run normalize+agent on each chunk in parallel; return all matched rows."""
    chunk_size = int(os.getenv("CHUNK_SIZE", str(_DEFAULT_CHUNK_SIZE)))
    n_chunks = max(1, math.ceil(len(all_rows) / chunk_size))
    chunks = [all_rows[i * chunk_size : (i + 1) * chunk_size] for i in range(n_chunks)]
    matched: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_process_chunk, chunk, context): i for i, chunk in enumerate(chunks)}
        for future in as_completed(futures):
            matched.extend(future.result())
    return matched
