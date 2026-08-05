"""Independent validation tools used by VerifierAgent.

The functions are deterministic, side-effect free, and trace through a callback.
They do not repair drafts or write output files.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from .audit import TraceEmitter, emit_tool_event
from .policy_tools import PolicyEvaluationError, evaluate_policy

MAX_MODEL_PARAMETERS = 10_000_000_000
REQUIRED_AGENT_IDS = {
    "coordinator_agent",
    "order_seller_agent",
    "payment_agent",
    "delivery_agent",
    "policy_agent",
    "verifier_agent",
}

PRIMARY_ISSUES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
}
CAUSE_CODES = {
    "SELLER_HANDOFF_AFTER_LIMIT",
    "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT",
    "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED",
    "DELIVERY_WITHIN_ESTIMATE",
}
ACTIONS = {
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
}
ISSUE_RULES = {
    "canceled_order_paid": {
        "cause": "ORDER_CANCELED_AFTER_PAYMENT",
        "action": "issue_full_refund",
        "party": ("platform", "OLIST_PLATFORM"),
        "refund_source": "payment_total_brl",
        "status": "action_required",
    },
    "unavailable_order_paid": {
        "cause": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        "action": "issue_full_refund",
        "party": ("platform", "OLIST_PLATFORM"),
        "refund_source": "payment_total_brl",
        "status": "action_required",
    },
    "late_delivery_seller": {
        "cause": "SELLER_HANDOFF_AFTER_LIMIT",
        "action": "refund_freight",
        "party_type": "seller",
        "refund_source": "freight_total_brl",
        "status": "action_required",
    },
    "late_delivery_logistics": {
        "cause": "CARRIER_DELIVERED_AFTER_ESTIMATE",
        "action": "refund_freight",
        "party": ("logistics_provider", "LOGISTICS_PROVIDER"),
        "refund_source": "freight_total_brl",
        "status": "action_required",
    },
    "valid_split_payment": {
        "cause": "MULTIPLE_PAYMENTS_RECONCILED",
        "action": "explain_valid_split_payment",
        "no_parties": True,
        "refund_source": None,
        "status": "no_action",
    },
    "unsupported_late_claim": {
        "cause": "DELIVERY_WITHIN_ESTIMATE",
        "action": "reject_late_refund",
        "no_parties": True,
        "refund_source": None,
        "status": "no_action",
    },
}

CASE_ID_RE = re.compile(r"^EC_\d{3}$")
ROW_ID_RE = re.compile(r"^[^:]+:[1-9]\d*$")
EVIDENCE_PATTERNS = (
    re.compile(r"^order:[^:]+$"),
    re.compile(r"^item:[^:]+:[1-9]\d*$"),
    re.compile(r"^payment:[^:]+:[1-9]\d*$"),
    re.compile(r"^seller:[^:]+$"),
    re.compile(r"^policy:(?:" + "|".join(sorted(CAUSE_CODES)) + r")$"),
)

EvidenceLookup = Callable[[str], bool]


def _error(
    code: str,
    path: str,
    message: str,
    *,
    expected: Any = None,
    actual: Any = None,
    repair_target: str = "policy_agent",
    repairable: bool = True,
) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "message": message,
        "expected": expected,
        "actual": actual,
        "repair_target": repair_target,
        "repairable": repairable,
    }


def _money(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _sequence(value: Any) -> Sequence[Any] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return None


def _validate_structure(output: Mapping[str, Any], errors: list[dict[str, Any]]) -> None:
    required_top = {
        "case_id",
        "assessment",
        "affected_entities",
        "root_cause_analysis",
        "evidence_ids",
        "financial_resolution",
        "resolution_actions",
    }
    for key in sorted(required_top - set(output)):
        errors.append(_error("SCHEMA_REQUIRED", key, "Required field is missing"))

    case_id = output.get("case_id")
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        errors.append(
            _error("SCHEMA_CASE_ID", "case_id", "Invalid case ID", expected="EC_###", actual=case_id)
        )

    assessment = _mapping(output.get("assessment"))
    if assessment is None:
        errors.append(_error("SCHEMA_TYPE", "assessment", "Must be an object"))
    else:
        if assessment.get("primary_issue") not in PRIMARY_ISSUES:
            errors.append(
                _error(
                    "SCHEMA_ENUM",
                    "assessment.primary_issue",
                    "Unsupported primary issue",
                    actual=assessment.get("primary_issue"),
                )
            )
        if assessment.get("case_status") not in {"action_required", "no_action"}:
            errors.append(
                _error(
                    "SCHEMA_ENUM",
                    "assessment.case_status",
                    "Unsupported case status",
                    actual=assessment.get("case_status"),
                )
            )
        confidence = assessment.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            errors.append(
                _error(
                    "SCHEMA_RANGE",
                    "assessment.confidence",
                    "Confidence must be within [0, 1]",
                    actual=confidence,
                )
            )

    entities = _mapping(output.get("affected_entities"))
    entity_specs = {
        "order_ids": re.compile(r"^[^:]+$"),
        "item_ids": ROW_ID_RE,
        "seller_ids": re.compile(r"^[^:]+$"),
        "payment_ids": ROW_ID_RE,
    }
    if entities is None:
        errors.append(_error("SCHEMA_TYPE", "affected_entities", "Must be an object"))
    else:
        for field, pattern in entity_specs.items():
            values = _sequence(entities.get(field))
            if values is None:
                errors.append(_error("SCHEMA_TYPE", f"affected_entities.{field}", "Must be an array"))
                continue
            if len(values) > 5:
                errors.append(
                    _error("SCHEMA_LIMIT", f"affected_entities.{field}", "At most 5 IDs are allowed", actual=len(values))
                )
            if len(values) != len(set(map(str, values))):
                errors.append(_error("SCHEMA_DUPLICATE", f"affected_entities.{field}", "IDs must be unique"))
            for index, value in enumerate(values):
                if not isinstance(value, str) or not pattern.fullmatch(value):
                    errors.append(
                        _error("SCHEMA_ID_FORMAT", f"affected_entities.{field}[{index}]", "Invalid ID format", actual=value)
                    )

    root = _mapping(output.get("root_cause_analysis"))
    if root is None:
        errors.append(_error("SCHEMA_TYPE", "root_cause_analysis", "Must be an object"))
    else:
        causes = _sequence(root.get("ranked_causes"))
        if causes is None:
            errors.append(_error("SCHEMA_TYPE", "root_cause_analysis.ranked_causes", "Must be an array"))
        else:
            if not 1 <= len(causes) <= 3:
                errors.append(_error("SCHEMA_LIMIT", "root_cause_analysis.ranked_causes", "Must contain 1 to 3 causes", actual=len(causes)))
            for index, cause in enumerate(causes):
                if not isinstance(cause, Mapping) or cause.get("cause_code") not in CAUSE_CODES:
                    errors.append(_error("SCHEMA_ENUM", f"root_cause_analysis.ranked_causes[{index}].cause_code", "Invalid cause code"))
                if not isinstance(cause, Mapping) or cause.get("rank") != index + 1:
                    errors.append(_error("SCHEMA_RANK", f"root_cause_analysis.ranked_causes[{index}].rank", "Ranks must be contiguous from 1"))
        parties = _sequence(root.get("responsible_parties"))
        if parties is None:
            errors.append(_error("SCHEMA_TYPE", "root_cause_analysis.responsible_parties", "Must be an array"))
        elif len(parties) > 3:
            errors.append(_error("SCHEMA_LIMIT", "root_cause_analysis.responsible_parties", "At most 3 parties are allowed", actual=len(parties)))
        else:
            for index, party in enumerate(parties):
                if not isinstance(party, Mapping) or party.get("party_type") not in {"seller", "platform", "logistics_provider"} or not party.get("party_id"):
                    errors.append(_error("SCHEMA_PARTY", f"root_cause_analysis.responsible_parties[{index}]", "Invalid responsible party"))

    evidence = _sequence(output.get("evidence_ids"))
    if evidence is None:
        errors.append(_error("SCHEMA_TYPE", "evidence_ids", "Must be an array"))
    else:
        if len(evidence) > 10:
            errors.append(_error("SCHEMA_LIMIT", "evidence_ids", "At most 10 evidence IDs are allowed", actual=len(evidence)))
        if len(evidence) != len(set(map(str, evidence))):
            errors.append(_error("SCHEMA_DUPLICATE", "evidence_ids", "Evidence IDs must be unique"))
        for index, value in enumerate(evidence):
            if not isinstance(value, str) or not any(pattern.fullmatch(value) for pattern in EVIDENCE_PATTERNS):
                errors.append(_error("EVIDENCE_FORMAT", f"evidence_ids[{index}]", "Invalid evidence ID", actual=value, repair_target="verifier_agent"))

    financial = _mapping(output.get("financial_resolution"))
    if financial is None:
        errors.append(_error("SCHEMA_TYPE", "financial_resolution", "Must be an object"))
    else:
        if financial.get("currency") != "BRL":
            errors.append(_error("SCHEMA_ENUM", "financial_resolution.currency", "Currency must be BRL", actual=financial.get("currency")))
        for field in ("item_total_brl", "freight_total_brl", "payment_total_brl", "recommended_refund_brl"):
            if _money(financial.get(field)) is None:
                errors.append(_error("FINANCIAL_INVALID", f"financial_resolution.{field}", "Must be finite and non-negative", actual=financial.get(field), repair_target="payment_agent"))

    actions = _sequence(output.get("resolution_actions"))
    if actions is None:
        errors.append(_error("SCHEMA_TYPE", "resolution_actions", "Must be an array"))
    else:
        if not 1 <= len(actions) <= 5:
            errors.append(_error("SCHEMA_LIMIT", "resolution_actions", "Must contain 1 to 5 actions", actual=len(actions)))
        for index, value in enumerate(actions):
            if value not in ACTIONS:
                errors.append(_error("SCHEMA_ENUM", f"resolution_actions[{index}]", "Invalid action", actual=value))


def _validate_policy_consistency(output: Mapping[str, Any], errors: list[dict[str, Any]]) -> None:
    assessment = _mapping(output.get("assessment")) or {}
    root = _mapping(output.get("root_cause_analysis")) or {}
    financial = _mapping(output.get("financial_resolution")) or {}
    issue = assessment.get("primary_issue")
    rule = ISSUE_RULES.get(issue)
    if not rule:
        return

    causes = _sequence(root.get("ranked_causes")) or []
    cause = causes[0].get("cause_code") if causes and isinstance(causes[0], Mapping) else None
    if cause != rule["cause"]:
        errors.append(_error("POLICY_CAUSE_MISMATCH", "root_cause_analysis.ranked_causes[0].cause_code", "Cause does not match primary issue", expected=rule["cause"], actual=cause))

    actions = _sequence(output.get("resolution_actions")) or []
    if list(actions) != [rule["action"]]:
        errors.append(_error("POLICY_ACTION_MISMATCH", "resolution_actions", "Action does not match primary issue", expected=[rule["action"]], actual=list(actions)))

    if assessment.get("case_status") != rule["status"]:
        errors.append(_error("POLICY_STATUS_MISMATCH", "assessment.case_status", "Status does not match primary issue", expected=rule["status"], actual=assessment.get("case_status")))

    if issue in {"valid_split_payment", "unsupported_late_claim"}:
        item_total = _money(financial.get("item_total_brl"))
        freight_total = _money(financial.get("freight_total_brl"))
        payment_total = _money(financial.get("payment_total_brl"))
        if item_total is not None and freight_total is not None and payment_total is not None:
            expected_payment = item_total + freight_total
            if abs(payment_total - expected_payment) > Decimal("0.10"):
                errors.append(
                    _error(
                        "FINANCIAL_TOTAL_MISMATCH",
                        "financial_resolution.payment_total_brl",
                        "Payment total is not reconciled with item + freight within 0.10 BRL",
                        expected=float(expected_payment),
                        actual=float(payment_total),
                        repair_target="payment_agent",
                    )
                )

    refund = _money(financial.get("recommended_refund_brl"))
    expected_refund = Decimal("0.00") if rule["refund_source"] is None else _money(financial.get(rule["refund_source"]))
    if refund is not None and expected_refund is not None and refund != expected_refund:
        errors.append(_error("FINANCIAL_REFUND_MISMATCH", "financial_resolution.recommended_refund_brl", "Refund does not match policy source total", expected=float(expected_refund), actual=float(refund), repair_target="policy_agent"))

    parties = list(_sequence(root.get("responsible_parties")) or [])
    if rule.get("no_parties") and parties:
        errors.append(_error("POLICY_PARTY_MISMATCH", "root_cause_analysis.responsible_parties", "This issue must not assign a responsible party", expected=[], actual=parties))
    if "party" in rule:
        expected = {"party_type": rule["party"][0], "party_id": rule["party"][1]}
        if parties != [expected]:
            errors.append(_error("POLICY_PARTY_MISMATCH", "root_cause_analysis.responsible_parties", "Responsible party does not match issue", expected=[expected], actual=parties))
    if rule.get("party_type") and (not parties or any(p.get("party_type") != rule["party_type"] for p in parties if isinstance(p, Mapping))):
        errors.append(_error("POLICY_PARTY_MISMATCH", "root_cause_analysis.responsible_parties", "Seller issue must assign seller parties", expected=rule["party_type"], actual=parties))


def verify_output(
    output: Mapping[str, Any],
    *,
    expected_case_id: str | None = None,
    evidence_lookup: EvidenceLookup | None = None,
    trace_emit: TraceEmitter | None = None,
    trace_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured Verifier result without mutating the draft."""

    started = perf_counter()
    errors: list[dict[str, Any]] = []
    if not isinstance(output, Mapping):
        errors.append(_error("SCHEMA_TYPE", "$", "Output must be an object", repairable=False))
    else:
        _validate_structure(output, errors)
        _validate_policy_consistency(output, errors)
        if expected_case_id is not None and output.get("case_id") != expected_case_id:
            errors.append(_error("SCHEMA_CASE_ID_MISMATCH", "case_id", "case_id does not match requested output", expected=expected_case_id, actual=output.get("case_id")))
        if evidence_lookup is not None:
            for index, evidence_id in enumerate(_sequence(output.get("evidence_ids")) or []):
                if isinstance(evidence_id, str) and any(pattern.fullmatch(evidence_id) for pattern in EVIDENCE_PATTERNS):
                    try:
                        exists = bool(evidence_lookup(evidence_id))
                    except Exception as exc:  # verifier must report lookup failure, not hide it
                        errors.append(_error("EVIDENCE_LOOKUP_FAILED", f"evidence_ids[{index}]", str(exc), repair_target="verifier_agent"))
                    else:
                        if not exists:
                            errors.append(_error("EVIDENCE_NOT_FOUND", f"evidence_ids[{index}]", "Evidence does not exist in source data", actual=evidence_id, repair_target="verifier_agent"))

    result = {
        "valid": not errors,
        "errors": errors,
        "repairable": bool(errors) and all(error["repairable"] for error in errors),
    }
    emit_tool_event(
        trace_emit,
        context=trace_context,
        event_type="TOOL_COMPLETED",
        stage="independent_verification",
        agent_id="verifier_agent",
        tool_name="verify_output",
        status="success" if result["valid"] else "rejected",
        duration_ms=int((perf_counter() - started) * 1000),
        input_value=output,
        output_value=result,
        error=None if result["valid"] else {"codes": [item["code"] for item in errors]},
    )
    return result


def _contract_error(code: str, path: str, message: str) -> dict[str, Any]:
    """Build an error compatible with the shared VerifyError contract."""

    return {
        "code": code,
        "path": path,
        "message": message,
        "repair_target": "policy_agent",
    }


def _normalized_contract_value(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    if isinstance(value, Mapping):
        return {key: _normalized_contract_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_normalized_contract_value(item) for item in value]
    return value


def verify_policy_decision(
    bundle: Any,
    decision: Any,
    *,
    trace_emit: TraceEmitter | None = None,
    trace_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently recompute policy and compare every contract field."""

    started = perf_counter()
    errors: list[dict[str, Any]] = []
    try:
        expected = evaluate_policy(bundle)
    except PolicyEvaluationError as exc:
        errors.append(
            _contract_error(exc.code, "bundle", f"Cannot verify unresolved bundle: {exc}")
        )
        expected = None

    actual = _normalized_contract_value(decision)
    if not isinstance(actual, Mapping):
        errors.append(_contract_error("VERIFY_DECISION_TYPE", "decision", "Decision must be an object"))
    elif expected is not None:
        normalized_expected = _normalized_contract_value(expected)
        fields = (
            "primary_issue",
            "case_status",
            "confidence",
            "ranked_causes",
            "responsible_parties",
            "recommended_refund_brl",
            "resolution_actions",
            "policy_evidence_ids",
        )
        for field in fields:
            expected_value = normalized_expected.get(field)
            actual_value = actual.get(field)
            if field == "recommended_refund_brl":
                expected_money = _money(expected_value)
                actual_money = _money(actual_value)
                matches = expected_money is not None and expected_money == actual_money
            else:
                matches = expected_value == actual_value
            if not matches:
                errors.append(
                    _contract_error(
                        "VERIFY_POLICY_MISMATCH",
                        f"decision.{field}",
                        f"Expected {expected_value!r}, got {actual_value!r}",
                    )
                )

    result = {"valid": not errors, "repairable": bool(errors), "errors": errors}
    emit_tool_event(
        trace_emit,
        context=trace_context,
        event_type="TOOL_COMPLETED",
        stage="independent_verification",
        agent_id="verifier_agent",
        tool_name="verify_policy",
        status="success" if result["valid"] else "rejected",
        duration_ms=int((perf_counter() - started) * 1000),
        input_value={"bundle": _normalized_contract_value(bundle), "decision": actual},
        output_value=result,
        error=None if result["valid"] else {"codes": [item["code"] for item in errors]},
    )
    return result


# Name declared in the VerifierAgent tool allowlist.
verify_policy = verify_policy_decision


def _agent_configs(metadata: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    agents = metadata.get("agents")
    if isinstance(agents, Mapping):
        return [dict(value, agent_id=key) if isinstance(value, Mapping) else {"agent_id": key} for key, value in agents.items()]
    if isinstance(agents, Sequence) and not isinstance(agents, (str, bytes)):
        return [value for value in agents if isinstance(value, Mapping)]
    return []


def validate_metadata(metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate model/audit metadata for all six logical agents.

    GPT-4o mini has no official parameter count published. A config with
    ``parameter_count: null`` is reported as unverified and cannot be promoted.
    """

    errors: list[dict[str, Any]] = []
    if not isinstance(metadata, Mapping):
        return [_error("METADATA_TYPE", "$", "Metadata must be an object", repair_target="coordinator_agent", repairable=False)]
    if not metadata.get("framework"):
        errors.append(_error("METADATA_REQUIRED", "framework", "Framework is required", repair_target="coordinator_agent", repairable=False))
    if not metadata.get("runtime"):
        errors.append(_error("METADATA_REQUIRED", "runtime", "Runtime is required", repair_target="coordinator_agent", repairable=False))

    configs = _agent_configs(metadata)
    present = {str(agent.get("agent_id")) for agent in configs if agent.get("agent_id")}
    for missing in sorted(REQUIRED_AGENT_IDS - present):
        errors.append(_error("METADATA_AGENT_MISSING", "agents", f"Missing agent metadata: {missing}", repair_target="coordinator_agent", repairable=False))

    for index, agent in enumerate(configs):
        path = f"agents[{index}]"
        agent_id = agent.get("agent_id")
        if not agent.get("model_name"):
            errors.append(_error("METADATA_MODEL_MISSING", f"{path}.model_name", "Model name is required", repair_target="coordinator_agent", repairable=False))
        count = agent.get("parameter_count")
        upper_bound = agent.get("parameter_count_upper_bound")
        has_valid_count = isinstance(count, int) and not isinstance(count, bool) and 0 < count <= MAX_MODEL_PARAMETERS
        has_valid_upper_bound = (
            isinstance(upper_bound, int)
            and not isinstance(upper_bound, bool)
            and 0 < upper_bound <= MAX_MODEL_PARAMETERS
            and agent.get("parameter_count_source") in {"official", "provider", "user_attested"}
        )
        if isinstance(count, int) and not isinstance(count, bool) and count > MAX_MODEL_PARAMETERS:
            errors.append(
                _error(
                    "MODEL_PARAMETER_LIMIT_EXCEEDED",
                    f"{path}.parameter_count",
                    f"{agent_id}: model exceeds the 10B limit",
                    expected=f"<= {MAX_MODEL_PARAMETERS}",
                    actual=count,
                    repair_target="coordinator_agent",
                    repairable=False,
                )
            )
        elif not has_valid_count and not has_valid_upper_bound:
            errors.append(
                _error(
                    "MODEL_PARAMETER_COUNT_UNVERIFIED",
                    f"{path}.parameter_count",
                    f"{agent_id}: a positive, evidenced parameter count is required",
                    actual={"parameter_count": count, "parameter_count_upper_bound": upper_bound},
                    repair_target="coordinator_agent",
                    repairable=False,
                )
            )
        if not agent.get("prompt_version"):
            errors.append(_error("METADATA_REQUIRED", f"{path}.prompt_version", "Prompt version is required", repair_target="coordinator_agent", repairable=False))
        tools = agent.get("tools") if "tools" in agent else agent.get("allowed_tools")
        if not isinstance(tools, list):
            errors.append(_error("METADATA_REQUIRED", f"{path}.tools", "Tool allowlist must be an array", repair_target="coordinator_agent", repairable=False))
        fallbacks = agent.get("fallback_models", [])
        if not isinstance(fallbacks, list):
            errors.append(_error("METADATA_FALLBACK_INVALID", f"{path}.fallback_models", "Fallback models must be an array", repair_target="coordinator_agent", repairable=False))
        else:
            for fallback_index, fallback in enumerate(fallbacks):
                fallback_count = fallback.get("parameter_count") if isinstance(fallback, Mapping) else None
                if not isinstance(fallback_count, int) or fallback_count <= 0 or fallback_count > MAX_MODEL_PARAMETERS:
                    errors.append(_error("METADATA_FALLBACK_UNVERIFIED", f"{path}.fallback_models[{fallback_index}]", "Every fallback must have an evidenced parameter count <=10B", actual=fallback, repair_target="coordinator_agent", repairable=False))
    return errors
