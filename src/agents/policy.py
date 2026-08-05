"""PolicyAgent: independent model invocation grounded by EC_POLICY_V1 tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._support import StructuredInvoker, load_prompt, require_tools, tool_trace_emitter
from src.contracts import AgentConfig, HandoffEnvelope, InvestigationBundle, PolicyDecision
from src.tools.policy_tools import evaluate_ec_policy_v1
from src.tracing import TraceSink

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "policy_v1.txt"


class PolicyAgent:
    REQUIRED_TOOLS = {"evaluate_ec_policy_v1", "assemble_output"}

    def __init__(
        self,
        structured_model: StructuredInvoker,
        config: AgentConfig,
        *,
        trace: TraceSink | None = None,
        prompt_path: Path = PROMPT_PATH,
    ) -> None:
        if config.agent_id != "policy_agent":
            raise ValueError("PolicyAgent requires policy_agent config")
        require_tools(config.allowed_tools, self.REQUIRED_TOOLS, agent_id=config.agent_id)
        self.structured_model = structured_model
        self.config = config
        self.trace = trace
        self.system_prompt = load_prompt(prompt_path)

    @classmethod
    def from_chat_model(
        cls, chat_model: Any, config: AgentConfig, *, trace: TraceSink | None = None
    ) -> "PolicyAgent":
        structured = chat_model.with_structured_output(
            PolicyDecision, method="json_schema", strict=True
        )
        return cls(structured, config, trace=trace)

    async def __call__(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        if envelope.receiver != "policy_agent" or envelope.message_type != "POLICY_REQUEST":
            raise ValueError("PolicyAgent only accepts POLICY_REQUEST addressed to policy_agent")

        bundle = InvestigationBundle.model_validate(envelope.payload)
        authoritative = PolicyDecision.model_validate(
            evaluate_ec_policy_v1(
                bundle,
                trace_emit=tool_trace_emitter(self.trace, envelope),
                trace_context={
                    "run_id": envelope.run_id,
                    "case_id": envelope.case_id,
                    "correlation_id": envelope.correlation_id,
                    "attempt": envelope.attempt,
                },
            )
        )
        payload = {
            "case_id": envelope.case_id,
            "investigation_bundle": bundle.model_dump(mode="json"),
            "authoritative_policy_tool_result": authoritative.model_dump(mode="json"),
        }
        model_result = await self.structured_model.ainvoke(
            [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            ]
        )
        decision = PolicyDecision.model_validate(model_result)
        if decision != authoritative:
            raise ValueError("PolicyAgent model output disagrees with authoritative EC_POLICY_V1 tool")
        return decision.model_dump(mode="json")
