from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agents.coordinator import CoordinatorAgent
from src.agents.stubs import stub_handlers
from src.batch import execute_batch
from src.preflight import run_preflight
from src.runtime import AgentRuntime
from src.tracing import TraceSink


ROOT = Path(__file__).resolve().parents[1]


class SelectiveFailureCoordinator:
    def __init__(self, delegate: CoordinatorAgent, failed_case_id: str) -> None:
        self.delegate = delegate
        self.runtime = delegate.runtime
        self.failed_case_id = failed_case_id

    async def run_stub(self, case, run_id, *, writer=None):
        if case.case_id == self.failed_case_id:
            raise RuntimeError("injected batch failure")
        return await self.delegate.run_stub(case, run_id, writer=writer)


def test_batch_isolates_one_case_failure_and_reaches_terminal_state(tmp_path: Path) -> None:
    all_cases, _ = run_preflight(ROOT)
    cases = {case_id: all_cases[case_id] for case_id in ("EC_001", "EC_002")}
    trace_path = tmp_path / "trace.jsonl"
    runtime = AgentRuntime(TraceSink(trace_path), stub_handlers())
    coordinator = SelectiveFailureCoordinator(
        CoordinatorAgent(runtime), failed_case_id="EC_002"
    )

    summary = asyncio.run(
        execute_batch(
            cases,
            coordinator,  # type: ignore[arg-type]
            run_id="batch-test",
            writer=None,
            concurrency=2,
        )
    )

    assert summary["received"] == 2
    assert summary["verified"] == 1
    assert summary["failed"] == 1
    assert summary["terminal"] == 2
    assert summary["missing_terminal_ids"] == []
    assert summary["missing_verified_ids"] == ["EC_002"]
    assert summary["success"] is False
    assert summary["errors"] == [
        {
            "case_id": "EC_002",
            "error_type": "RuntimeError",
            "message": "injected batch failure",
        }
    ]
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert any(
        event["case_id"] == "EC_002" and event["event"] == "case_failed"
        for event in events
    )


def test_batch_rejects_unsafe_concurrency(tmp_path: Path) -> None:
    cases, _ = run_preflight(ROOT)
    runtime = AgentRuntime(TraceSink(tmp_path / "trace.jsonl"), stub_handlers())

    with pytest.raises(ValueError, match="between 1 and 16"):
        asyncio.run(
            execute_batch(
                {"EC_001": cases["EC_001"]},
                CoordinatorAgent(runtime),
                run_id="batch-test",
                writer=None,
                concurrency=0,
            )
        )
