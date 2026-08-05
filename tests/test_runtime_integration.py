from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agents.coordinator import CoordinatorAgent
from src.agents.order_seller import OrderSellerAgent
from src.agents.payment import PaymentAgent
from src.agents.registry import build_hybrid_handlers
from src.contracts import HandoffEnvelope
from src.preflight import run_preflight
from src.runtime import AgentRuntime
from src.output_writer import AtomicOutputWriter
from src.tracing import TraceSink


ROOT = Path(__file__).resolve().parents[1]


def request(receiver: str = "payment_agent") -> HandoffEnvelope:
    return HandoffEnvelope(
        run_id="runtime-test",
        case_id="EC_001",
        correlation_id="runtime-correlation",
        sender="coordinator_agent",
        receiver=receiver,
        message_type="TASK_REQUEST",
        payload={"claimed_order_id": "a" * 32},
    )


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_runtime_retries_only_the_failed_invocation_once(tmp_path: Path) -> None:
    calls: list[int] = []

    async def flaky(envelope: HandoffEnvelope) -> dict:
        calls.append(envelope.attempt)
        if len(calls) == 1:
            raise TimeoutError("temporary timeout")
        return {"ok": True}

    trace_path = tmp_path / "trace.jsonl"
    runtime = AgentRuntime(TraceSink(trace_path), {"payment_agent": flaky}, max_retries=1)
    result = asyncio.run(runtime.invoke(request()))
    assert result == {"ok": True}
    assert calls == [0, 1]
    events = read_events(trace_path)
    assert [event["event"] for event in events].count("retry_scheduled") == 1
    assert events[-1]["attempt"] == 1


def test_runtime_does_not_retry_contract_errors(tmp_path: Path) -> None:
    calls = 0

    async def invalid(_: HandoffEnvelope) -> dict:
        nonlocal calls
        calls += 1
        raise ValueError("invalid contract")

    runtime = AgentRuntime(
        TraceSink(tmp_path / "trace.jsonl"), {"payment_agent": invalid}, max_retries=1
    )
    with pytest.raises(ValueError, match="invalid contract"):
        asyncio.run(runtime.invoke(request()))
    assert calls == 1


def test_hybrid_flow_uses_real_tv4_tv5_boundaries(tmp_path: Path) -> None:
    cases, _ = run_preflight(ROOT)
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceSink(trace_path)
    handlers = build_hybrid_handlers(trace)
    runtime = AgentRuntime(trace, handlers)
    result = asyncio.run(CoordinatorAgent(runtime).run_stub(cases["EC_001"], "hybrid-test"))
    assert result.state == "VERIFIED"
    assert isinstance(handlers["order_seller_agent"].__self__, OrderSellerAgent)
    assert isinstance(handlers["payment_agent"].__self__, PaymentAgent)
    assert handlers["delivery_agent"].__name__ == "delivery_agent_handler"
    events = read_events(trace_path)
    agents = {event["agent"] for event in events}
    assert {
        "coordinator_agent",
        "order_seller_agent",
        "payment_agent",
        "delivery_agent",
        "policy_agent",
        "verifier_agent",
    } <= agents
    assert any(event["event"] == "tool_completed" for event in events)


def test_hybrid_flow_can_atomically_write_only_verified_draft(tmp_path: Path) -> None:
    cases, _ = run_preflight(ROOT)
    trace = TraceSink(tmp_path / "trace.jsonl")
    runtime = AgentRuntime(trace, build_hybrid_handlers(trace))
    writer = AtomicOutputWriter(tmp_path / "output")
    result = asyncio.run(
        CoordinatorAgent(runtime).run_stub(
            cases["EC_001"], "hybrid-write-test", writer=writer
        )
    )
    assert result.state == "VERIFIED"
    assert result.output_path is not None
    output_path = Path(result.output_path)
    assert output_path.name == "EC_001.json"
    assert json.loads(output_path.read_text(encoding="utf-8"))["case_id"] == "EC_001"
