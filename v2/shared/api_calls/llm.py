"""The ONE way this codebase calls an LLM — TypeSafe AI jev via Vercel AI Gateway.

Usage:
    from v2.shared.api_calls.llm import decide, NoulQuestion, ChoiceQuestion, BudgetExceeded

    answers = decide(
        state={"title": "Controls Engineer", "company": "Siemens Energy", ...},
        questions={
            "company_match": NoulQuestion(
                instructions="Does this job belong to one of the target companies?",
                criteria={"true": "Company matches", "false": "Company does not match"},
            ),
            "location": ChoiceQuestion(
                instructions="Which location?",
                criteria={"wigan": "Wigan", "none": "None"},
            ),
        },
        purpose="job_matching",
    )
    answers["company_match"].noul   # float [0, 1] — probability of True
    answers["location"].choice      # e.g. "wigan"

Provider: typesafe-ai/jev via Vercel AI Gateway (.env → AI_GATEWAY_API_KEY).
Every call is logged to runs/<run>/llm_calls.jsonl (tokens, GBP cost, purpose).
Hard stop at £3.00 (BudgetExceeded raised before sending).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import ai
from ai.ops.experimental import (  # re-exported for callers
    ChoiceAnswer,
    ChoiceQuestion,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    evaluate,
)

BUDGET_GBP = 3.00
USD_TO_GBP = 0.79
_JEV_INPUT_PRICE_USD_PER_M = 0.042  # output tokens are free

_MODEL_ID = "typesafe-ai/jev"

_run_dir: Path | None = None
_budget_lock = threading.Lock()
_model: Any = None
_in_flight_cost: float = 0.0  # sum of worst-case costs for concurrent in-flight calls


class BudgetExceeded(RuntimeError):
    """The £3.00 hard stop would be passed. Nothing was sent."""


def start_run(run_dir: Path) -> None:
    """Called by the handler: this run's calls are logged in run_dir/llm_calls.jsonl."""
    global _run_dir
    _run_dir = run_dir


def _runs_root() -> Path:
    return Path(os.environ.get("ILLUMINI_RUNS_DIR", "runs"))


def spent_gbp() -> float:
    """Total spend so far, across every run folder."""
    total = 0.0
    for ledger in _runs_root().glob("*/llm_calls.jsonl"):
        with ledger.open(encoding="utf-8") as f:
            total += sum(json.loads(line)["cost_gbp"] for line in f if line.strip())
    return total


def _load_env(path: Path = Path(".env")) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _ensure_gateway_key() -> None:
    _load_env()
    jev_key = os.environ.get("AI_GATEWAY_API_KEY", "")
    if not jev_key:
        raise RuntimeError("No jev key: set AI_GATEWAY_API_KEY in .env")
    os.environ.setdefault("AI_GATEWAY_API_KEY", jev_key)


def _get_model() -> Any:
    global _model
    if _model is None:
        _ensure_gateway_key()
        _model = ai.get_model(_MODEL_ID)
    return _model


def _cost_gbp(input_tokens: int) -> float:
    return input_tokens * _JEV_INPUT_PRICE_USD_PER_M / 1_000_000 * USD_TO_GBP


def _estimate_tokens(state: dict, questions: dict) -> int:
    state_chars = sum(len(str(v)) for v in state.values())
    question_chars = sum(len(str(q)) for q in questions.values())
    return (state_chars + question_chars) // 4


def _guard(estimated_tokens: int) -> tuple[float, float]:
    """Check budget, reserve worst-case cost. Returns (total_spent, reserved).
    Caller must call _release_in_flight(reserved) in a finally block."""
    global _in_flight_cost
    total = spent_gbp()
    worst = _cost_gbp(estimated_tokens)
    if total + _in_flight_cost + worst > BUDGET_GBP:
        raise BudgetExceeded(
            f"LLM budget: £{total:.4f} spent + £{_in_flight_cost:.4f} in-flight, "
            f"this call ~£{worst:.4f}, cap £{BUDGET_GBP:.2f}"
        )
    _in_flight_cost += worst
    return total, worst


def _release_in_flight(reserved: float) -> None:
    global _in_flight_cost
    _in_flight_cost = max(0.0, _in_flight_cost - reserved)


async def _evaluate_async(state: dict, questions: dict) -> tuple[dict, int]:
    item = await evaluate(_get_model(), state, questions)
    input_tokens = item.usage.input_tokens if item.usage else 0
    return item.value, input_tokens


def _safe_json(obj: Any) -> Any:
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(x) for x in obj]
    try:
        return {k: _safe_json(v) for k, v in vars(obj).items()}
    except TypeError:
        return str(obj)


def _log_call(
    rd: Path,
    started: float,
    total: float,
    purpose: str,
    input_tokens: int,
    state: dict | None = None,
    questions: dict | None = None,
    answers: dict | None = None,
) -> None:
    cost = _cost_gbp(input_tokens)
    latency = round((time.time() - started) * 1000)
    rd.mkdir(parents=True, exist_ok=True)
    with _budget_lock:
        with (rd / "llm_calls.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": round(started, 3),
                        "provider": "jev",
                        "model": _MODEL_ID,
                        "purpose": purpose,
                        "input_tokens": input_tokens,
                        "output_tokens": 0,
                        "cost_gbp": round(cost, 6),
                        "total_gbp": round(total + cost, 6),
                        "latency_ms": latency,
                    }
                )
                + "\n"
            )
        if state is not None or questions is not None or answers is not None:
            with (rd / "llm_prompts.jsonl").open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": round(started, 3),
                            "purpose": purpose,
                            "latency_ms": latency,
                            "state": _safe_json(state),
                            "questions": _safe_json(questions),
                            "answers": _safe_json(answers),
                        }
                    )
                    + "\n"
                )


def decide(
    state: dict[str, Any],
    questions: dict[str, NoulQuestion | ChoiceQuestion | ScoreQuestion],
    purpose: str = "",
) -> dict[str, NoulAnswer | ChoiceAnswer | ScoreAnswer]:
    """Ask jev to answer structured questions about `state` (synchronous, sequential).

    answers["key"].noul    — NoulAnswer: probability float [0, 1]
    answers["key"].choice  — ChoiceAnswer: chosen option key string
    answers["key"].score   — ScoreAnswer: float score
    """
    estimated = _estimate_tokens(state, questions)
    with _budget_lock:
        total, reserved = _guard(estimated)

    started = time.time()
    try:
        answers, input_tokens = asyncio.run(_evaluate_async(state, questions))
    finally:
        with _budget_lock:
            _release_in_flight(reserved)

    rd = _run_dir or (_runs_root() / time.strftime("%Y%m%dT%H%M%S", time.gmtime(started)))
    _log_call(rd, started, total, purpose, input_tokens, state, questions, answers)
    return answers


async def decide_async(
    state: dict[str, Any],
    questions: dict[str, NoulQuestion | ChoiceQuestion | ScoreQuestion],
    purpose: str = "",
) -> dict[str, NoulAnswer | ChoiceAnswer | ScoreAnswer]:
    """Ask jev to answer structured questions about `state` (async, safe for asyncio.gather).

    Must be called from within an active event loop — use asyncio.run() at the top level.
    """
    estimated = _estimate_tokens(state, questions)
    with _budget_lock:
        total, reserved = _guard(estimated)

    started = time.time()
    try:
        answers, input_tokens = await _evaluate_async(state, questions)
    finally:
        with _budget_lock:
            _release_in_flight(reserved)

    rd = _run_dir or (_runs_root() / time.strftime("%Y%m%dT%H%M%S", time.gmtime(started)))
    _log_call(rd, started, total, purpose, input_tokens, state, questions, answers)
    return answers
