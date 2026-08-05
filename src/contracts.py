"""Versioned contracts shared by all six logical agents."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CASE_ID_PATTERN = r"^EC_\d{3}$"
ORDER_ID_PATTERN = r"^[0-9a-f]{32}$"
MAX_MODEL_PARAMETERS = 10_000_000_000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseInput(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    opened_at: datetime
    claimed_order_id: str = Field(pattern=ORDER_ID_PATTERN)
    policy_version: Literal["EC_POLICY_V1"]
    message: str = Field(min_length=1)
    language: str = "vi"


class AgentConfig(StrictModel):
    agent_id: str
    role: str
    model_name: str
    parameter_count: int | None = Field(default=None, gt=0, le=MAX_MODEL_PARAMETERS)
    parameter_count_upper_bound: int | None = Field(default=None, gt=0, le=MAX_MODEL_PARAMETERS)
    parameter_count_source: Literal["official", "provider", "user_attested"]
    prompt_version: str
    allowed_tools: list[str]
    input_schema: str
    output_schema: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @field_validator("parameter_count_upper_bound")
    @classmethod
    def require_parameter_evidence(cls, value: int | None, info: Any) -> int | None:
        if info.data.get("parameter_count") is None and value is None:
            raise ValueError("parameter_count or a <=10B upper bound is required")
        return value


class RuntimeConfig(StrictModel):
    schema_version: Literal["1.0"]
    framework: Literal["langgraph"]
    runtime: str
    agents: list[AgentConfig]

    @field_validator("agents")
    @classmethod
    def validate_six_unique_agents(cls, value: list[AgentConfig]) -> list[AgentConfig]:
        ids = [agent.agent_id for agent in value]
        if len(ids) != 6 or len(set(ids)) != 6:
            raise ValueError("exactly six unique agent configs are required")
        return value


MessageType = Literal[
    "TASK_REQUEST",
    "FACT_RESPONSE",
    "POLICY_REQUEST",
    "DECISION_RESPONSE",
    "VERIFY_REQUEST",
    "VERIFY_RESULT",
    "REPAIR_REQUEST",
    "ERROR_RESPONSE",
]


class HandoffEnvelope(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    correlation_id: str
    sender: str
    receiver: str
    message_type: MessageType
    attempt: int = Field(default=0, ge=0, le=1)
    payload: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class ItemFact(StrictModel):
    order_item_id: int = Field(gt=0)
    seller_id: str
    shipping_limit_date: datetime | None = None
    price_brl: Decimal = Decimal("0")
    freight_brl: Decimal = Decimal("0")


class OrderSellerFacts(StrictModel):
    order_id: str = Field(pattern=ORDER_ID_PATTERN)
    order_status: str
    delivered_carrier_at: datetime | None = None
    delivered_customer_at: datetime | None = None
    estimated_delivery_at: datetime | None = None
    items: list[ItemFact] = Field(default_factory=list)
    item_total_brl: Decimal = Decimal("0")
    freight_total_brl: Decimal = Decimal("0")
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class PaymentRowFact(StrictModel):
    payment_sequential: int = Field(gt=0)
    payment_type: str
    payment_installments: int = Field(ge=0)
    payment_value_brl: Decimal = Decimal("0")


class PaymentFacts(StrictModel):
    order_id: str = Field(pattern=ORDER_ID_PATTERN)
    payments: list[PaymentRowFact] = Field(default_factory=list)
    payment_total_brl: Decimal = Decimal("0")
    payment_count: int = Field(ge=0)
    reconciliation_delta_brl: Decimal = Decimal("0")
    is_reconciled_within_0_10: bool | None = None
    is_reconciled: bool | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def normalize_reconciliation_flag(self) -> "PaymentFacts":
        if self.is_reconciled_within_0_10 is None and self.is_reconciled is None:
            raise ValueError("a payment reconciliation flag is required")
        if self.is_reconciled_within_0_10 is None:
            self.is_reconciled_within_0_10 = self.is_reconciled
        if self.is_reconciled is None:
            self.is_reconciled = self.is_reconciled_within_0_10
        return self


class SellerHandoffViolation(StrictModel):
    order_item_id: int | None = Field(default=None, gt=0)
    seller_id: str
    shipping_limit_date: datetime | None = None
    delivered_carrier_at: datetime | None = None


class DeliveryFacts(StrictModel):
    order_id: str = Field(pattern=ORDER_ID_PATTERN)
    is_delivered_late: bool | None = None
    is_late: bool | None = None
    late_stage: Literal["seller", "logistics", "not_late", "undetermined"]
    seller_handoff_violations: list[SellerHandoffViolation] = Field(
        default_factory=list, max_length=5
    )
    violating_seller_ids: list[str] = Field(default_factory=list, max_length=5)
    delivered_carrier_at: datetime | None = None
    delivered_customer_at: datetime | None = None
    estimated_delivery_at: datetime | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_delivery_fields(self) -> "DeliveryFacts":
        if self.is_delivered_late is None and self.is_late is None:
            if self.late_stage != "undetermined":
                raise ValueError("a delivery late flag is required")
        if self.is_delivered_late is None:
            self.is_delivered_late = self.is_late
        if self.is_late is None:
            self.is_late = self.is_delivered_late
        if not self.seller_handoff_violations and self.violating_seller_ids:
            self.seller_handoff_violations = [
                SellerHandoffViolation(seller_id=seller_id)
                for seller_id in self.violating_seller_ids
            ]
        if not self.violating_seller_ids and self.seller_handoff_violations:
            self.violating_seller_ids = sorted(
                {violation.seller_id for violation in self.seller_handoff_violations}
            )[:5]
        return self


class InvestigationBundle(StrictModel):
    policy_version: Literal["EC_POLICY_V1"]
    case: CaseInput
    order_seller: OrderSellerFacts
    payment: PaymentFacts
    delivery: DeliveryFacts
    warnings: list[str] = Field(default_factory=list)


class RankedCause(StrictModel):
    cause_code: str
    rank: int = Field(ge=1, le=3)


class ResponsibleParty(StrictModel):
    party_type: str
    party_id: str


class PolicyDecision(StrictModel):
    policy_version: Literal["EC_POLICY_V1"] = "EC_POLICY_V1"
    primary_issue: str
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    ranked_causes: list[RankedCause] = Field(max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(max_length=3)
    recommended_refund_brl: Decimal = Decimal("0")
    resolution_actions: list[str] = Field(max_length=5)
    policy_evidence_ids: list[str] = Field(max_length=3)
    matched_rule_rank: int = Field(ge=1, le=6)


class VerifyError(StrictModel):
    code: str
    path: str = ""
    message: str
    repair_target: str | None = None
    repairable: bool = True
    expected: Any | None = None
    actual: Any | None = None


class VerifyResult(StrictModel):
    valid: bool
    repairable: bool = False
    errors: list[VerifyError] = Field(default_factory=list)


class TraceEvent(StrictModel):
    run_id: str
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    correlation_id: str
    agent: str
    event: str
    timestamp: datetime
    sender: str | None = None
    receiver: str | None = None
    attempt: int = Field(default=0, ge=0, le=1)
    duration_ms: int = Field(default=0, ge=0)
    status: Literal["started", "succeeded", "failed"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class CaseRunResult(StrictModel):
    run_id: str
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    correlation_id: str
    state: Literal["VERIFIED", "FAILED"]
    verify_result: VerifyResult
    stub: bool = True
