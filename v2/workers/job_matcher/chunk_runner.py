"""Split the job feed into chunks and run normalize+agent on each in parallel.

One asyncio event loop drives the whole run. A single asyncio.Semaphore caps the
total number of concurrent JEV calls across all chunks — replacing the old pattern
of 16 threads × their own per-chunk semaphores (which could spike to 160 calls).

Normalization is synchronous and CPU-light; it runs in the default thread-pool via
run_in_executor so it doesn't block the event loop.
"""

from __future__ import annotations

import asyncio
import importlib
import math
import os

from v2.shared.patterns.worker_runtime import validate_context

_DEFAULT_CHUNK_SIZE = 500
_DEFAULT_CONCURRENCY = 500


async def _process_chunk(chunk: list[dict], context: dict, sem: asyncio.Semaphore) -> list[dict]:
    loop = asyncio.get_running_loop()
    stage_normalise = importlib.import_module("v2.workers.job_matcher.stages.stage_normalise")
    stage_agent = importlib.import_module("v2.workers.job_matcher.stages.stage_agent")
    match_jobs = importlib.import_module("v2.workers.job_matcher.agent.match_jobs")

    r = await loop.run_in_executor(None, stage_normalise.main, context, chunk)
    validate_context(context, stage_agent.INPUT_CONTEXT_SCHEMA)
    result = await match_jobs.main_async(context, r.data, sem=sem)
    validate_context(context, stage_agent.OUTPUT_CONTEXT_SCHEMA)
    return result.data


async def _run_all(all_rows: list[dict], context: dict, chunk_size: int) -> list[dict]:
    concurrency = int(os.getenv("LLM_CONCURRENCY", str(_DEFAULT_CONCURRENCY)))
    sem = asyncio.Semaphore(concurrency)
    n_chunks = max(1, math.ceil(len(all_rows) / chunk_size))
    chunks = [all_rows[i * chunk_size : (i + 1) * chunk_size] for i in range(n_chunks)]
    results = await asyncio.gather(*[_process_chunk(chunk, context, sem) for chunk in chunks])
    return [row for chunk_rows in results for row in chunk_rows]


def run_chunks(all_rows: list[dict], context: dict) -> list[dict]:
    """Run normalize+agent on all chunks; return all matched rows."""
    chunk_size = int(os.getenv("CHUNK_SIZE", str(_DEFAULT_CHUNK_SIZE)))
    return asyncio.run(_run_all(all_rows, context, chunk_size))
