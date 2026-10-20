"""The £3.00 LLM hard stop is a hard raise. These tests never touch the network: the provider call is faked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from v1.shared.api_calls import llm


@pytest.fixture
def fake_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Anthropic key set, every call costs exactly 1,000 prompt + 1,000 completion tokens, nothing is sent."""
    sent: list[str] = []
    monkeypatch.setenv("ILLUMINI_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_SENIOR_DEVELOPER_KEY", "test-key")
    monkeypatch.setattr(llm, "_run_dir", tmp_path / "run")

    def fake_send(name: str, prompt: str, max_tokens: int, schema: dict | None) -> tuple[str, int, int, str]:
        sent.append(prompt)
        return ('{"city": "Leeds"}' if schema else "Leeds"), 1000, 1000, "end_turn"

    monkeypatch.setattr(llm, "_send", fake_send)
    return sent


def write_spend(tmp_path: Path, gbp: float) -> None:
    (tmp_path / "earlier_run").mkdir(exist_ok=True)
    (tmp_path / "earlier_run" / "llm_calls.jsonl").write_text(json.dumps({"cost_gbp": gbp}) + "\n", encoding="utf-8")


def test_calls_are_logged_with_cost_and_purpose(fake_llm: list[str], tmp_path: Path) -> None:
    assert llm.ask("where?", purpose="locate") == "Leeds"
    assert llm.ask_json("where?", schema={"type": "object"}, purpose="locate") == {"city": "Leeds"}
    logged = [json.loads(line) for line in (tmp_path / "run" / "llm_calls.jsonl").read_text().splitlines()]
    assert [r["purpose"] for r in logged] == ["locate", "locate"]
    assert logged[0]["cost_gbp"] == pytest.approx(llm.cost_gbp("anthropic", 1000, 1000), abs=1e-6)


def test_raises_once_the_hard_stop_is_spent(fake_llm: list[str], tmp_path: Path) -> None:
    write_spend(tmp_path, llm.BUDGET_GBP)
    with pytest.raises(llm.BudgetExceeded):
        llm.ask("never sent")
    assert fake_llm == []


def test_raises_before_a_call_that_could_cross_the_hard_stop(fake_llm: list[str], tmp_path: Path) -> None:
    worst_case = llm.cost_gbp("anthropic", 10, 500)
    write_spend(tmp_path, llm.BUDGET_GBP - worst_case / 2)
    with pytest.raises(llm.BudgetExceeded):
        llm.ask("x" * 20)
    assert fake_llm == []


def test_spending_up_to_the_cap_then_stops(fake_llm: list[str], tmp_path: Path) -> None:
    calls = 0
    with pytest.raises(llm.BudgetExceeded):
        while True:
            llm.ask("where?", max_tokens=1000)
            calls += 1
    assert llm.spent_gbp() <= llm.BUDGET_GBP
    assert calls == len(fake_llm) > 0
