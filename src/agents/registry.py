"""TV1 handler registries for staged integration."""

from __future__ import annotations

import json
from typing import Any

from src.agents.delivery import delivery_agent_handler
from src.agents.policy import PolicyAgent
from src.agents.stubs import stub_handlers
from src.agents.verifier import VerifierAgent
from src.config import load_runtime_config
from src.contracts import AgentConfig
from src.tracing import TraceSink


class AuthoritativeEchoInvoker:
    """Offline CP2 model double that echoes the deterministic tool result."""

    def __init__(self, response_key: str) -> None:
        self.response_key = response_key

    async def ainvoke(self, messages: Any) -> Any:
        payload = json.loads(messages[-1].content)
        return payload[self.response_key]


def _agent_config(agent_id: str) -> AgentConfig:
    return next(agent for agent in load_runtime_config().agents if agent.agent_id == agent_id)


def build_hybrid_handlers(trace: TraceSink) -> dict[str, Any]:
    """Use real TV4/TV5 agents while TV2/TV3 remain contract-safe stubs."""
    handlers = stub_handlers()
    handlers["delivery_agent"] = delivery_agent_handler
    handlers["policy_agent"] = PolicyAgent(
        AuthoritativeEchoInvoker("authoritative_policy_tool_result"),
        _agent_config("policy_agent"),
        trace=trace,
    )
    handlers["verifier_agent"] = VerifierAgent(
        AuthoritativeEchoInvoker("authoritative_verification_tool_result"),
        _agent_config("verifier_agent"),
        trace=trace,
    )
    return handlers
