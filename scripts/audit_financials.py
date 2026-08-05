"""Checkpoint 5 (TV3): audit item/freight/payment/refund on all 50 real cases.

Independently recomputes every money field in output/EC_*.json straight from
data/*.csv via src/finance.py + src/tools/payment_tools.py - never trusting
the pipeline's own numbers - and writes a machine-readable report plus a
human-readable "Financial audit summary" for submission.

Usage:
    .venv\\Scripts\\python.exe scripts/audit_financials.py
    .venv\\Scripts\\python.exe scripts/audit_financials.py --output-dir output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.finance import to_money
from src.tools.payment_tools import get_order_financial_reference, get_order_payments, reconcile_payments

REFUND_SOURCE = {
    "canceled_order_paid": "payment_total_brl",
    "unavailable_order_paid": "payment_total_brl",
    "late_delivery_seller": "freight_total_brl",
    "late_delivery_logistics": "freight_total_brl",
    "valid_split_payment": None,
    "unsupported_late_claim": None,
}
RECONCILE_ISSUES = {"valid_split_payment", "unsupported_late_claim"}
TOLERANCE = Decimal("0.10")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _load_outputs(output_dir: Path) -> list[dict[str, Any]]:
    cases = []
    for path in sorted(output_dir.glob("EC_*.json")):
        with path.open("r", encoding="utf-8") as handle:
            cases.append(json.load(handle))
    return cases


def audit_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    order_id = case["affected_entities"]["order_ids"][0] if case["affected_entities"]["order_ids"] else None
    issue = case["assessment"]["primary_issue"]
    financial = case["financial_resolution"]
    findings: list[str] = []

    if order_id is None:
        return {"case_id": case_id, "order_id": None, "issue": issue, "findings": ["NO_ORDER_ID"]}

    reference = get_order_financial_reference(order_id)
    payment_rows = get_order_payments(order_id)
    recomputed_payment_total = sum((row["payment_value_brl"] for row in payment_rows), Decimal("0.00"))

    item_total = to_money(financial["item_total_brl"])
    freight_total = to_money(financial["freight_total_brl"])
    payment_total = to_money(financial["payment_total_brl"])
    refund = to_money(financial["recommended_refund_brl"])

    if item_total != reference["item_total_brl"]:
        findings.append(f"ITEM_TOTAL_MISMATCH: output={item_total} recomputed={reference['item_total_brl']}")
    if freight_total != reference["freight_total_brl"]:
        findings.append(f"FREIGHT_TOTAL_MISMATCH: output={freight_total} recomputed={reference['freight_total_brl']}")
    if payment_total != recomputed_payment_total:
        findings.append(f"PAYMENT_TOTAL_MISMATCH: output={payment_total} recomputed={recomputed_payment_total}")

    source_field = REFUND_SOURCE.get(issue)
    expected_refund = Decimal("0.00") if source_field is None else to_money(financial.get(source_field, 0))
    if refund != expected_refund:
        findings.append(f"REFUND_SOURCE_MISMATCH: issue={issue} refund={refund} expected={expected_refund}")

    if issue in RECONCILE_ISSUES:
        delta = abs(payment_total - (item_total + freight_total))
        if delta > TOLERANCE:
            findings.append(f"TOLERANCE_VIOLATION: delta={delta} > {TOLERANCE}")

    for field in ("item_total_brl", "freight_total_brl", "payment_total_brl", "recommended_refund_brl"):
        raw = financial[field]
        if to_money(raw) != Decimal(str(raw)):
            findings.append(f"ROUNDING_MISMATCH: field={field} value={raw}")

    bundle = reconcile_payments(order_id, payment_rows, financial["payment_total_brl"])
    output_payment_ids = {pid for pid in case["evidence_ids"] if pid.startswith(f"payment:{order_id}:")}
    valid_ids = set(bundle["evidence_ids"])
    unbacked = sorted(output_payment_ids - valid_ids)
    if unbacked:
        findings.append(f"EVIDENCE_NOT_BACKED: {unbacked}")

    return {
        "case_id": case_id,
        "order_id": order_id,
        "primary_issue": issue,
        "item_total_brl": str(item_total),
        "freight_total_brl": str(freight_total),
        "payment_total_brl": str(payment_total),
        "recommended_refund_brl": str(refund),
        "findings": findings,
    }


def audit_financials(output_dir: Path) -> dict[str, Any]:
    cases = _load_outputs(output_dir)
    results = [audit_case(case) for case in cases]
    mismatched = [result for result in results if result["findings"]]

    issue_counts: dict[str, int] = {}
    for result in results:
        issue = result.get("primary_issue")
        if issue:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

    return {
        "cases_audited": len(results),
        "cases_clean": len(results) - len(mismatched),
        "cases_with_findings": len(mismatched),
        "primary_issue_distribution": dict(sorted(issue_counts.items())),
        "results": results,
    }


def render_summary(report: dict[str, Any]) -> str:
    mismatched = [r for r in report["results"] if r["findings"]]
    findings_rows = "\n".join(
        f"| `{r['case_id']}` | {r['order_id']} | {'; '.join(r['findings'])} |" for r in mismatched
    ) or "| _none_ | - | - |"
    issue_rows = "\n".join(
        f"| `{issue}` | {count} |" for issue, count in report["primary_issue_distribution"].items()
    ) or "| _none_ | 0 |"

    return f"""# Financial audit summary (TV3, Checkpoint 5)

Recompute doc lap item_total_brl, freight_total_brl, payment_total_brl va
recommended_refund_brl cho toan bo 50 case that trong `output/`, doi chieu
truc tiep voi `data/*.csv` bang `src/finance.py` + `src/tools/payment_tools.py`
(khong doc lai so co san trong output).

## Outcome

| Metric | Value |
| --- | ---: |
| Cases audited | {report['cases_audited']} |
| Cases clean (0 finding) | {report['cases_clean']} |
| Cases with findings | {report['cases_with_findings']} |

## Primary issue distribution

| primary_issue | count |
| --- | ---: |
{issue_rows}

## Findings

| case_id | order_id | findings |
| --- | --- | --- |
{findings_rows}

## Checks performed per case

1. `item_total_brl` / `freight_total_brl` == sum of `olist_order_items_dataset.csv` rows for the order.
2. `payment_total_brl` == sum of `olist_order_payments_dataset.csv` rows (never multiplied by `payment_installments`).
3. `recommended_refund_brl` matches its EC_POLICY_V1 source (`payment_total_brl` / `freight_total_brl` / `0.00`) for the case's `primary_issue`.
4. `valid_split_payment` / `unsupported_late_claim`: `|payment_total - (item_total+freight_total)| <= 0.10 BRL`.
5. All four money fields are 2-decimal, `ROUND_HALF_UP`.
6. Every `payment:<order_id>:<seq>` evidence ID in the output is backed by a real payment row.

## Go/no-go for financial fields

{"**GO** - 0 findings across 50/50 cases." if not mismatched else f"**NO-GO** - {len(mismatched)} case(s) need payment/finance fixes before submission, see table above."}
"""


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT / "output"), help="Directory with EC_*.json files")
    parser.add_argument(
        "--summary-path",
        default=str(ROOT / "docs" / "checkpoints" / "tv3-financial-audit-summary.md"),
        help="Where to write the human-readable summary",
    )
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "logging" / "tv3_financial_audit.json"),
        help="Where to write the machine-readable report",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"audit_financials: output dir not found: {output_dir}", file=sys.stderr)
        return 1

    report = audit_financials(output_dir)
    _atomic_write(Path(args.report_path), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(Path(args.summary_path), render_summary(report))

    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    return 0 if report["cases_with_findings"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
