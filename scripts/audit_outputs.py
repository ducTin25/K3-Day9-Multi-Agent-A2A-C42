"""Read-only, independent audit of the 50 submission JSON files.

This module deliberately does not import production agents, policy tools,
repository adapters, or verifier code. It rebuilds its oracle from raw CSV so
a shared production bug cannot make both generation and audit pass together.
The proxy score follows README category weights but is not the hidden grader.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
MONEY = Decimal("0.01")
TOLERANCE = Decimal("0.10")
CATEGORY_WEIGHTS = {
    "assessment": Decimal("20"),
    "affected_entities": Decimal("20"),
    "root_cause": Decimal("15"),
    "evidence": Decimal("15"),
    "financial": Decimal("20"),
    "actions": Decimal("10"),
}
RULES = {
    "canceled_order_paid": (
        "ORDER_CANCELED_AFTER_PAYMENT",
        [("platform", "OLIST_PLATFORM")],
        "issue_full_refund",
    ),
    "unavailable_order_paid": (
        "ORDER_UNAVAILABLE_AFTER_PAYMENT",
        [("platform", "OLIST_PLATFORM")],
        "issue_full_refund",
    ),
    "late_delivery_seller": (
        "SELLER_HANDOFF_AFTER_LIMIT",
        None,
        "refund_freight",
    ),
    "late_delivery_logistics": (
        "CARRIER_DELIVERED_AFTER_ESTIMATE",
        [("logistics_provider", "LOGISTICS_PROVIDER")],
        "refund_freight",
    ),
    "valid_split_payment": (
        "MULTIPLE_PAYMENTS_RECONCILED",
        [],
        "explain_valid_split_payment",
    ),
    "unsupported_late_claim": (
        "DELIVERY_WITHIN_ESTIMATE",
        [],
        "reject_late_refund",
    ),
}


def _money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(MONEY, rounding=ROUND_HALF_UP)


def _timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _load_cases(input_dir: Path) -> dict[str, str]:
    cases: dict[str, str] = {}
    for path in sorted(input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        case_id = payload["case_id"]
        order_id = payload.get("claimed_order_id") or payload["customer_request"][
            "claimed_order_id"
        ]
        cases[case_id] = order_id
    return cases


def _read_filtered(
    path: Path, order_ids: set[str], *, key: str = "order_id"
) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get(key) in order_ids]


def _load_raw_oracle(data_dir: Path, cases: dict[str, str]) -> dict[str, Any]:
    order_ids = set(cases.values())
    orders = {
        row["order_id"]: row
        for row in _read_filtered(data_dir / "olist_orders_dataset.csv", order_ids)
    }
    items: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_filtered(data_dir / "olist_order_items_dataset.csv", order_ids):
        items[row["order_id"]].append(row)
    payments: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _read_filtered(data_dir / "olist_order_payments_dataset.csv", order_ids):
        payments[row["order_id"]].append(row)
    seller_ids = {row["seller_id"] for rows in items.values() for row in rows}
    with (data_dir / "olist_sellers_dataset.csv").open(encoding="utf-8", newline="") as handle:
        sellers = {
            row["seller_id"]
            for row in csv.DictReader(handle)
            if row["seller_id"] in seller_ids
        }
    return {"orders": orders, "items": items, "payments": payments, "sellers": sellers}


def _expected(case_id: str, order_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    order = raw["orders"][order_id]
    items = sorted(
        raw["items"].get(order_id, []), key=lambda row: int(row["order_item_id"])
    )
    payments = sorted(
        raw["payments"].get(order_id, []),
        key=lambda row: int(row["payment_sequential"]),
    )
    item_total = sum((_money(row["price"]) for row in items), Decimal("0.00"))
    freight_total = sum(
        (_money(row["freight_value"]) for row in items), Decimal("0.00")
    )
    payment_total = sum(
        (_money(row["payment_value"]) for row in payments), Decimal("0.00")
    )
    reconciled = abs(payment_total - item_total - freight_total) <= TOLERANCE
    delivered = _timestamp(order.get("order_delivered_customer_date"))
    estimated = _timestamp(order.get("order_estimated_delivery_date"))
    carrier = _timestamp(order.get("order_delivered_carrier_date"))
    is_late = bool(delivered and estimated and delivered > estimated)
    violating_sellers = sorted(
        {
            row["seller_id"]
            for row in items
            if carrier
            and _timestamp(row.get("shipping_limit_date"))
            and carrier > _timestamp(row["shipping_limit_date"])
        }
    )

    status = order["order_status"].lower()
    if status == "canceled" and payment_total > 0:
        issue = "canceled_order_paid"
        refund = payment_total
    elif status == "unavailable" and payment_total > 0:
        issue = "unavailable_order_paid"
        refund = payment_total
    elif is_late and violating_sellers:
        issue = "late_delivery_seller"
        refund = freight_total
    elif is_late:
        issue = "late_delivery_logistics"
        refund = freight_total
    elif len(payments) >= 2 and reconciled:
        issue = "valid_split_payment"
        refund = Decimal("0.00")
    elif is_late is False and reconciled:
        issue = "unsupported_late_claim"
        refund = Decimal("0.00")
    else:
        issue = "POLICY_UNRESOLVED"
        refund = Decimal("0.00")

    cause, fixed_parties, action = RULES.get(issue, (None, [], None))
    parties = (
        [("seller", seller_id) for seller_id in violating_sellers[:3]]
        if issue == "late_delivery_seller"
        else fixed_parties
    )
    entity_items = [f"{order_id}:{row['order_item_id']}" for row in items[:5]]
    entity_sellers = sorted({row["seller_id"] for row in items})[:5]
    entity_payments = [
        f"{order_id}:{row['payment_sequential']}" for row in payments[:5]
    ]
    expected_evidence = [f"policy:{cause}", f"order:{order_id}"]
    expected_evidence += [f"item:{value}" for value in entity_items]
    expected_evidence += [f"payment:{value}" for value in entity_payments]
    responsible_sellers = [party_id for party_type, party_id in parties if party_type == "seller"]
    expected_evidence += [f"seller:{value}" for value in responsible_sellers]
    expected_evidence += [
        f"seller:{value}" for value in entity_sellers if value not in responsible_sellers
    ]
    expected_evidence = list(dict.fromkeys(expected_evidence))[:10]
    return {
        "case_id": case_id,
        "issue": issue,
        "case_status": "action_required" if refund > 0 else "no_action",
        "cause": cause,
        "parties": parties,
        "action": action,
        "entities": {
            "order_ids": [order_id],
            "item_ids": entity_items,
            "seller_ids": entity_sellers,
            "payment_ids": entity_payments,
        },
        "financial": {
            "currency": "BRL",
            "item_total_brl": item_total,
            "freight_total_brl": freight_total,
            "payment_total_brl": payment_total,
            "recommended_refund_brl": refund,
        },
        "evidence": expected_evidence,
        "raw_ids": {
            "items": {f"item:{order_id}:{row['order_item_id']}" for row in items},
            "payments": {
                f"payment:{order_id}:{row['payment_sequential']}" for row in payments
            },
            "sellers": {f"seller:{row['seller_id']}" for row in items},
            "order": {f"order:{order_id}"},
            "policy": {f"policy:{cause}"} if cause else set(),
        },
    }


def _set_score(actual: Iterable[Any], expected: Iterable[Any], weight: Decimal) -> Decimal:
    actual_set, expected_set = set(actual), set(expected)
    if not actual_set and not expected_set:
        return weight
    union = actual_set | expected_set
    return weight * Decimal(len(actual_set & expected_set)) / Decimal(len(union))


def _audit_case(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    output = json.loads(path.read_text(encoding="utf-8"))
    findings: list[dict[str, str]] = []
    scores = {name: Decimal("0") for name in CATEGORY_WEIGHTS}

    assessment = output.get("assessment", {})
    issue_ok = assessment.get("primary_issue") == expected["issue"]
    status_ok = assessment.get("case_status") == expected["case_status"]
    confidence = assessment.get("confidence")
    confidence_valid = (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and 0 <= float(confidence) <= 1
    )
    scores["assessment"] = Decimal("12") * issue_ok + Decimal("4") * status_ok + Decimal("4") * confidence_valid
    if not issue_ok:
        findings.append({"category": "assessment", "message": f"primary_issue expected {expected['issue']}, got {assessment.get('primary_issue')}"})
    if not status_ok:
        findings.append({"category": "assessment", "message": f"case_status expected {expected['case_status']}, got {assessment.get('case_status')}"})

    entities = output.get("affected_entities", {})
    for field, expected_ids in expected["entities"].items():
        field_score = _set_score(entities.get(field, []), expected_ids, Decimal("5"))
        scores["affected_entities"] += field_score
        if field_score != Decimal("5"):
            findings.append({"category": "affected_entities", "message": f"{field} expected {expected_ids}, got {entities.get(field, [])}"})

    root = output.get("root_cause_analysis", {})
    causes = root.get("ranked_causes", [])
    actual_cause = causes[0].get("cause_code") if causes else None
    actual_parties = [
        (item.get("party_type"), item.get("party_id"))
        for item in root.get("responsible_parties", [])
    ]
    cause_ok = actual_cause == expected["cause"]
    party_score = _set_score(actual_parties, expected["parties"], Decimal("7.5"))
    scores["root_cause"] = Decimal("7.5") * cause_ok + party_score
    if not cause_ok:
        findings.append({"category": "root_cause", "message": f"cause expected {expected['cause']}, got {actual_cause}"})
    if party_score != Decimal("7.5"):
        findings.append({"category": "root_cause", "message": f"parties expected {expected['parties']}, got {actual_parties}"})

    evidence = output.get("evidence_ids", [])
    valid_evidence = set().union(*expected["raw_ids"].values())
    invalid_evidence = sorted(set(evidence) - valid_evidence)
    evidence_score = _set_score(evidence, expected["evidence"], CATEGORY_WEIGHTS["evidence"])
    if invalid_evidence:
        evidence_score *= Decimal("0.5")
        findings.append({"category": "evidence", "message": f"IDs not found in raw data/policy: {invalid_evidence}"})
    missing_evidence = sorted(set(expected["evidence"]) - set(evidence))
    if missing_evidence:
        findings.append({"category": "evidence", "message": f"recommended evidence missing: {missing_evidence}"})
    scores["evidence"] = evidence_score

    financial = output.get("financial_resolution", {})
    for field, expected_value in expected["financial"].items():
        actual = financial.get(field)
        matches = actual == expected_value if field == "currency" else _money(actual) == expected_value
        scores["financial"] += Decimal("4") * matches
        if not matches:
            findings.append({"category": "financial", "message": f"{field} expected {expected_value}, got {actual}"})

    actions = output.get("resolution_actions", [])
    action_ok = actions == [expected["action"]]
    scores["actions"] = CATEGORY_WEIGHTS["actions"] * action_ok
    if not action_ok:
        findings.append({"category": "actions", "message": f"expected {[expected['action']]}, got {actions}"})

    proxy_score = sum(scores.values(), Decimal("0"))
    return {
        "case_id": expected["case_id"],
        "file": path.name,
        "proxy_score": float(proxy_score.quantize(Decimal("0.0001"))),
        "category_scores": {key: float(value.quantize(Decimal("0.0001"))) for key, value in scores.items()},
        "findings": findings,
        "confidence": confidence,
    }


def audit_outputs(input_dir: Path, data_dir: Path, output_dir: Path) -> dict[str, Any]:
    cases = _load_cases(input_dir)
    raw = _load_raw_oracle(data_dir, cases)
    results: list[dict[str, Any]] = []
    missing_files: list[str] = []
    for case_id, order_id in sorted(cases.items()):
        path = output_dir / f"{case_id}.json"
        if not path.exists():
            missing_files.append(path.name)
            continue
        results.append(_audit_case(path, _expected(case_id, order_id, raw)))

    confidence_values = [item["confidence"] for item in results]
    category_totals = {
        category: sum(item["category_scores"][category] for item in results) / len(results)
        if results
        else 0.0
        for category in CATEGORY_WEIGHTS
    }
    return {
        "audit_version": "independent-raw-csv-v1",
        "disclaimer": "Proxy score; hidden grader confidence/evidence formulas are unknown.",
        "case_count": len(cases),
        "output_count": len(results),
        "missing_files": missing_files,
        "proxy_average": round(sum(item["proxy_score"] for item in results) / len(results), 4) if results else 0.0,
        "category_average": {key: round(value, 4) for key, value in category_totals.items()},
        "finding_counts": dict(sorted(Counter(finding["category"] for item in results for finding in item["findings"]).items())),
        "confidence_audit": {
            "unique_values": sorted(set(confidence_values)),
            "all_identical": len(set(confidence_values)) <= 1,
            "extreme_one_count": sum(value == 1.0 for value in confidence_values),
            "risk": "Hidden grader may reward calibrated confidence; run one-variable A/B candidates." if confidence_values and len(set(confidence_values)) == 1 else None,
        },
        "cases": results,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    rows = [
        "# Independent output audit",
        "",
        f"- Outputs: {report['output_count']}/{report['case_count']}",
        f"- Proxy average: **{report['proxy_average']}**",
        f"- Missing files: {len(report['missing_files'])}",
        f"- Disclaimer: {report['disclaimer']}",
        "",
        "## Category averages",
        "",
        "| Category | Proxy points | README weight |",
        "| --- | ---: | ---: |",
    ]
    for category, weight in CATEGORY_WEIGHTS.items():
        rows.append(f"| {category} | {report['category_average'][category]} | {weight} |")
    rows += [
        "",
        "## Confidence risk",
        "",
        f"- Unique values: `{report['confidence_audit']['unique_values']}`",
        f"- Values equal to 1.0: {report['confidence_audit']['extreme_one_count']}",
        f"- Note: {report['confidence_audit']['risk'] or 'No uniform-confidence risk detected.'}",
        "",
        "## Cases with findings",
        "",
    ]
    flagged = [item for item in report["cases"] if item["findings"]]
    if not flagged:
        rows.append("No raw-data mismatch found. The remaining leaderboard gap is likely in hidden confidence/evidence scoring.")
    for item in sorted(flagged, key=lambda value: value["proxy_score"]):
        rows.append(f"### {item['case_id']} — {item['proxy_score']}")
        rows.extend(f"- **{finding['category']}**: {finding['message']}" for finding in item["findings"])
        rows.append("")
    return "\n".join(rows).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "input")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports" / "output-audit")
    args = parser.parse_args()
    report = audit_outputs(args.input_dir, args.data_dir, args.output_dir)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.report_dir / "audit.md").write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("output_count", "proxy_average", "finding_counts", "confidence_audit")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
