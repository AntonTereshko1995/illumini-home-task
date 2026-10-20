"""The ONE way this codebase calls an LLM. Budget £1 for the whole task; hard stop at £3.00.

    from v2.shared.api_calls.llm import ask, ask_json, BudgetExceeded
    summary = ask("Summarise this job title in three words: ...", purpose="title_summary")
    data = ask_json("...", schema={"type": "object", "properties": {...}, "required": [...],
                                   "additionalProperties": False}, purpose="...")

Provider: Anthropic if ANTHROPIC_SENIOR_DEVELOPER_KEY is set, else Gemini (GEMINI_SENIOR_DEVELOPER_KEY).
Every call is logged to runs/<run>/llm_calls.jsonl (tokens, cost, your `purpose`). Spend is summed across
EVERY run folder. Before each call the worst case (prompt + max_tokens) is added to the total; if that
would pass £3.00, BudgetExceeded is raised and nothing is sent. There is no override.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

BUDGET_GBP = 3.00  # hard stop; the task budget is £1 (spend above it is questioned)
USD_TO_GBP = 0.79
DEFAULT_MAX_TOKENS = 500
CHARS_PER_TOKEN_WORST_CASE = 2.5  # conservative: real English is ~4 chars per token
PROVIDERS: dict[str, dict] = {
    # USD per million tokens. Thinking tokens are billed as output.
    "anthropic": {"key": "ANTHROPIC_SENIOR_DEVELOPER_KEY", "model": "claude-opus-5-5", "in": 4.00, "out": 20.00},
    "gemini": {"key": "GEMINI_SENIOR_DEVELOPER_KEY", "model": "gemini-3.5-flash", "in": 0.30, "out": 2.50},
}

_run_dir: Path | None = None
_clients: dict[str, object] = {}


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
    """KEY=value lines from .env into the environment (values already set in the shell win)."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def provider() -> str:
    """'anthropic' if its key is set (shell or .env), else 'gemini'."""
    _load_env()
    for name, spec in PROVIDERS.items():
        if os.environ.get(spec["key"]):
            return name
    raise RuntimeError("No LLM key: set ANTHROPIC_SENIOR_DEVELOPER_KEY or GEMINI_SENIOR_DEVELOPER_KEY in .env")


def cost_gbp(name: str, prompt_tokens: int, completion_tokens: int) -> float:
    spec = PROVIDERS[name]
    return (prompt_tokens * spec["in"] + completion_tokens * spec["out"]) / 1_000_000 * USD_TO_GBP


def _guard(name: str, prompt: str, max_tokens: int) -> float:
    """Raise BudgetExceeded unless the worst case of this call still fits under £3.00. Returns spend so far."""
    total = spent_gbp()
    worst = cost_gbp(name, int(len(prompt) / CHARS_PER_TOKEN_WORST_CASE) + 1, max_tokens)
    if total + worst > BUDGET_GBP:
        raise BudgetExceeded(
            f"LLM budget: £{total:.4f} spent, this call could cost up to £{worst:.4f}, cap £{BUDGET_GBP:.2f}"
        )
    return total


def _send(name: str, prompt: str, max_tokens: int, schema: dict | None) -> tuple[str, int, int, str]:
    """One provider call -> (text, prompt_tokens, completion_tokens, stop_reason)."""
    spec = PROVIDERS[name]
    if name == "anthropic":
        import anthropic

        client = _clients.setdefault(name, anthropic.Anthropic(api_key=os.environ[spec["key"]]))
        output_config: dict = {"effort": "low"}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        response = client.messages.create(
            model=spec["model"],
            max_tokens=max_tokens,
            output_config=output_config,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, response.usage.input_tokens, response.usage.output_tokens, str(response.stop_reason)
    from google import genai
    from google.genai import types

    client = _clients.setdefault(name, genai.Client(api_key=os.environ[spec["key"]]))
    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=0.0,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        **({"response_mime_type": "application/json", "response_json_schema": schema} if schema else {}),
    )
    response = client.models.generate_content(model=spec["model"], contents=prompt, config=config)
    usage = response.usage_metadata
    completion = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
    finish = response.candidates[0].finish_reason if response.candidates else None
    return response.text or "", usage.prompt_token_count or 0, completion, str(finish)


def _call(prompt: str, max_tokens: int, purpose: str, schema: dict | None) -> str:
    name = provider()
    total = _guard(name, prompt, max_tokens)
    started = time.time()
    text, prompt_tokens, completion_tokens, stop_reason = _send(name, prompt, max_tokens, schema)
    cost = cost_gbp(name, prompt_tokens, completion_tokens)
    run_dir = _run_dir or (_runs_root() / time.strftime("%Y%m%dT%H%M%S", time.gmtime(started)))
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "llm_calls.jsonl").open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": round(started, 3),
                    "provider": name,
                    "model": PROVIDERS[name]["model"],
                    "purpose": purpose,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_gbp": round(cost, 6),
                    "total_gbp": round(total + cost, 6),
                    "stop_reason": stop_reason,
                    "latency_ms": round((time.time() - started) * 1000),
                }
            )
            + "\n"
        )
    return text.strip()


def ask(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, purpose: str = "") -> str:
    """Send one prompt, get the text reply. `purpose` is logged so the spend can be read back."""
    return _call(prompt, max_tokens, purpose, None)


def ask_json(prompt: str, schema: dict, max_tokens: int = DEFAULT_MAX_TOKENS, purpose: str = "") -> dict:
    """Send one prompt, get a dict that matches `schema` (a JSON Schema object with additionalProperties false)."""
    return json.loads(_call(prompt, max_tokens, purpose, schema))
