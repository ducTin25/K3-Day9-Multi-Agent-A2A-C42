"""VerifierAgent: independent model context and deterministic policy cross-check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._support import StructuredInvoker, load_prompt, require_tools, tool_trace_emitter
from src.contracts import (
    AgentConfig,
    HandoffEnvelope,
    InvestigationBundle,
    PolicyDecision,
    VerifyResult,
)
from src.tools.verification_tools import verify_policy
from src.tracing import TraceSink

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "verifier_v1.txt"


class VerifierAgent:
    REQUIRED_TOOLS = {"verify_policy"}

    def __init__(
        self,
        structured_model: StructuredInvoker,
        config: AgentConfig,
        *,
        trace: TraceSink | None = None,
        prompt_path: Path = PROMPT_PATH,
    ) -> None:
        if config.agent_id != "verifier_agent":
            raise ValueError("VerifierAgent requires verifier_agent config")
        require_tools(config.allowed_tools, self.REQUIRED_TOOLS, agent_id=config.agent_id)
        self.structured_model = structured_model
        self.config = config
        self.trace = trace
        self.system_prompt = load_prompt(prompt_path)

    @classmethod
    def from_chat_model(
        cls, chat_model: Any, config: AgentConfig, *, trace: TraceSink | None = None
    ) -> "VerifierAgent":
        structured = chat_model.with_structured_output(
            VerifyResult, method="json_schema", strict=True
        )
        return cls(structured, config, trace=trace)

    async def __call__(self, envelope: HandoffEnvelope) -> dict[str, Any]:
        if envelope.receiver != "verifier_agent" or envelope.message_type != "VERIFY_REQUEST":
            raise ValueError("VerifierAgent only accepts VERIFY_REQUEST addressed to verifier_agent")

        raw_bundle = envelope.payload.get("bundle")
        raw_decision = envelope.payload.get("decision")
        bundle = InvestigationBundle.model_validate(raw_bundle)
        decision = PolicyDecision.model_validate(raw_decision)
        authoritative = VerifyResult.model_validate(
            verify_policy(
                bundle,
                decision,
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
            "policy_decision": decision.model_dump(mode="json"),
            "authoritative_verification_tool_result": authoritative.model_dump(mode="json"),
        }
        model_result = await self.structured_model.ainvoke(
            [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            ]
        )
        verification = VerifyResult.model_validate(model_result)
        if verification != authoritative:
            raise ValueError("VerifierAgent model output disagrees with deterministic verification tools")
        return verification.model_dump(mode="json")
