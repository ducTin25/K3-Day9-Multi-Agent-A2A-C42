import asyncio
import json
from pathlib import Path

from src.agents.coordinator import CoordinatorAgent
from src.agents.stubs import stub_handlers
from src.preflight import run_preflight
from src.runtime import AgentRuntime
from src.tracing import TraceSink


ROOT = Path(__file__).resolve().parents[1]


def test_stub_flow_invokes_all_six_agents(tmp_path: Path) -> None:
    cases, _ = run_preflight(ROOT)
    trace_path = tmp_path / "trace.jsonl"
    coordinator = CoordinatorAgent(AgentRuntime(TraceSink(trace_path), stub_handlers()))
    result = asyncio.run(coordinator.run_stub(cases["EC_001"], "test-run"))
    assert result.state == "VERIFIED"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    agents = {event["agent"] for event in events}
    assert agents == {
        "coordinator_agent",
        "order_seller_agent",
        "payment_agent",
        "delivery_agent",
        "policy_agent",
        "verifier_agent",
    }
    assert not (ROOT / "output" / "EC_001.json").exists()

