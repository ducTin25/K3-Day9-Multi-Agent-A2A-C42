"""Factory for the two independent TV5 runtime handlers."""

from __future__ import annotations

from typing import Any, Callable

from src.agents._support import tool_trace_emitter
from src.agents.policy import PolicyAgent
from src.agents.verifier import VerifierAgent
from src.contracts import (
    AgentConfig,
    HandoffEnvelope,
    InvestigationBundle,
    PolicyDecision,
    RuntimeConfig,
)
from src.models import build_chat_model
from src.tools.output_tools import assemble_output
from src.tracing import TraceSink


def _config(runtime: RuntimeConfig, agent_id: str) -> AgentConfig:
    return next(agent for agent in runtime.agents if agent.agent_id == agent_id)


def build_tv5_handlers(
    runtime: RuntimeConfig,
    trace: TraceSink,
    *,
    model_factory: Callable[[AgentConfig], Any] = build_chat_model,
) -> dict[str, Any]:
    """Build separate model clients and contexts for Policy and Verifier."""

    policy_config = _config(runtime, "policy_agent")
    verifier_config = _config(runtime, "verifier_agent")
    policy = PolicyAgent.from_chat_model(model_factory(policy_config), policy_config, trace=trace)
    verifier = VerifierAgent.from_chat_model(
        model_factory(verifier_config), verifier_config, trace=trace
    )
    return {"policy_agent": policy, "verifier_agent": verifier}


def assemble_tv5_draft(
    bundle: InvestigationBundle,
    decision: PolicyDecision,
    policy_envelope: HandoffEnvelope,
    trace: TraceSink,
) -> dict[str, Any]:
    """Public TV1 integration seam for schema assembly plus sanitized trace."""

    if (
        policy_envelope.receiver != "policy_agent"
        or policy_envelope.message_type != "POLICY_REQUEST"
    ):
        raise ValueError("draft assembly requires its originating POLICY_REQUEST envelope")
    return assemble_output(
        bundle,
        decision,
        trace_emit=tool_trace_emitter(trace, policy_envelope),
        trace_context={
            "run_id": policy_envelope.run_id,
            "case_id": policy_envelope.case_id,
            "correlation_id": policy_envelope.correlation_id,
            "attempt": policy_envelope.attempt,
        },
    )
