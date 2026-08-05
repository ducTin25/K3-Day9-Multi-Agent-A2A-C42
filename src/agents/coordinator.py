"""LangGraph Coordinator: orchestration only, with no domain logic."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from src.contracts import (
    CaseInput,
    CaseRunResult,
    DeliveryFacts,
    HandoffEnvelope,
    InvestigationBundle,
    OrderSellerFacts,
    PaymentFacts,
    PolicyDecision,
    TraceEvent,
    VerifyResult,
)
from src.runtime import AgentRuntime


class CoordinatorState(TypedDict, total=False):
    case: CaseInput
    run_id: str
    correlation_id: str
    order_seller: OrderSellerFacts
    payment: PaymentFacts
    delivery: DeliveryFacts
    bundle: InvestigationBundle
    decision: PolicyDecision
    verify_result: VerifyResult


class CoordinatorAgent:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime
        graph = StateGraph(CoordinatorState)
        graph.add_node("fan_out_domains", self._fan_out_domains)
        graph.add_node("invoke_policy", self._invoke_policy)
        graph.add_node("invoke_verifier", self._invoke_verifier)
        graph.add_edge(START, "fan_out_domains")
        graph.add_edge("fan_out_domains", "invoke_policy")
        graph.add_edge("invoke_policy", "invoke_verifier")
        graph.add_edge("invoke_verifier", END)
        self.graph = graph.compile()

    def _envelope(
        self,
        state: CoordinatorState,
        receiver: str,
        message_type: str,
        payload: dict[str, Any],
        evidence_ids: list[str] | None = None,
    ) -> HandoffEnvelope:
        return HandoffEnvelope(
            run_id=state["run_id"],
            case_id=state["case"].case_id,
            correlation_id=state["correlation_id"],
            sender="coordinator_agent",
            receiver=receiver,
            message_type=message_type,
            payload=payload,
            evidence_ids=evidence_ids or [],
        )

    async def _fan_out_domains(self, state: CoordinatorState) -> dict[str, Any]:
        case_payload = state["case"].model_dump(mode="json")
        requests = [
            self._envelope(state, "order_seller_agent", "TASK_REQUEST", case_payload),
            self._envelope(state, "payment_agent", "TASK_REQUEST", case_payload),
            self._envelope(state, "delivery_agent", "TASK_REQUEST", case_payload),
        ]
        order_raw, payment_raw, delivery_raw = await asyncio.gather(
            *(self.runtime.invoke(request) for request in requests)
        )
        order = OrderSellerFacts.model_validate(order_raw)
        payment = PaymentFacts.model_validate(payment_raw)
        delivery = DeliveryFacts.model_validate(delivery_raw)
        bundle = InvestigationBundle(
            policy_version=state["case"].policy_version,
            case=state["case"],
            order_seller=order,
            payment=payment,
            delivery=delivery,
        )
        return {"order_seller": order, "payment": payment, "delivery": delivery, "bundle": bundle}

    async def _invoke_policy(self, state: CoordinatorState) -> dict[str, Any]:
        evidence = sorted(
            set(
                state["order_seller"].evidence_ids
                + state["payment"].evidence_ids
                + state["delivery"].evidence_ids
            )
        )[:10]
        envelope = self._envelope(
            state,
            "policy_agent",
            "POLICY_REQUEST",
            state["bundle"].model_dump(mode="json"),
            evidence,
        )
        raw = await self.runtime.invoke(envelope)
        return {"decision": PolicyDecision.model_validate(raw)}

    async def _invoke_verifier(self, state: CoordinatorState) -> dict[str, Any]:
        payload = {
            "case": state["case"].model_dump(mode="json"),
            "bundle": state["bundle"].model_dump(mode="json"),
            "decision": state["decision"].model_dump(mode="json"),
            "stub": True,
        }
        envelope = self._envelope(state, "verifier_agent", "VERIFY_REQUEST", payload)
        raw = await self.runtime.invoke(envelope)
        return {"verify_result": VerifyResult.model_validate(raw)}

    async def run_stub(self, case: CaseInput, run_id: str) -> CaseRunResult:
        correlation_id = str(uuid4())
        self.runtime.trace.emit(
            TraceEvent(
                run_id=run_id,
                case_id=case.case_id,
                correlation_id=correlation_id,
                agent="coordinator_agent",
                event="case_received",
                timestamp=datetime.now(timezone.utc),
                status="started",
            )
        )
        result = await self.graph.ainvoke(
            {"case": case, "run_id": run_id, "correlation_id": correlation_id}
        )
        verify = result["verify_result"]
        state = "VERIFIED" if verify.valid else "FAILED"
        self.runtime.trace.emit(
            TraceEvent(
                run_id=run_id,
                case_id=case.case_id,
                correlation_id=correlation_id,
                agent="coordinator_agent",
                event="case_completed",
                timestamp=datetime.now(timezone.utc),
                status="succeeded" if verify.valid else "failed",
                output_summary={"state": state, "stub": True},
            )
        )
        return CaseRunResult(
            run_id=run_id,
            case_id=case.case_id,
            correlation_id=correlation_id,
            state=state,
            verify_result=verify,
            stub=True,
        )
