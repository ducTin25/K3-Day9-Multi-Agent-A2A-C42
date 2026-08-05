"""Payment tools and financial reconciliation for PaymentAgent (Member 3 / TV3)."""

import csv
import os
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.finance import is_within_tolerance, reconciliation_delta, sum_money, to_money


def get_order_payments(
    order_id: str, data_dir: Optional[str] = None, repository: Any = None
) -> List[Dict[str, Any]]:
    """Retrieve every payment row for a given order_id, sorted by payment_sequential.

    payment_value_brl is the full amount of that payment row (README muc 2);
    it is never multiplied by payment_installments here or downstream.
    """
    if repository and hasattr(repository, "get_order_payments"):
        return repository.get_order_payments(order_id)

    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    payments_csv = os.path.join(data_dir, "olist_order_payments_dataset.csv")
    rows: List[Dict[str, Any]] = []
    if os.path.exists(payments_csv):
        with open(payments_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("order_id") == order_id:
                    rows.append(
                        {
                            "payment_sequential": int(row.get("payment_sequential") or 0),
                            "payment_type": row.get("payment_type", ""),
                            "payment_installments": int(row.get("payment_installments") or 0),
                            "payment_value_brl": to_money(row.get("payment_value") or "0"),
                        }
                    )

    rows.sort(key=lambda r: r["payment_sequential"])
    return rows


def get_order_financial_reference(
    order_id: str, data_dir: Optional[str] = None, repository: Any = None
) -> Dict[str, Decimal]:
    """Retrieve item_total_brl + freight_total_brl for an order from order_items.

    Used as the reconciliation reference for payments (README muc 4: split
    payment tong phai khop item + freight). If the order has no item row,
    both totals are 0.00 (README muc 6).
    """
    if repository and hasattr(repository, "get_order_financial_reference"):
        return repository.get_order_financial_reference(order_id)

    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    items_csv = os.path.join(data_dir, "olist_order_items_dataset.csv")
    prices: List[str] = []
    freights: List[str] = []
    if os.path.exists(items_csv):
        with open(items_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("order_id") == order_id:
                    prices.append(row.get("price") or "0")
                    freights.append(row.get("freight_value") or "0")

    item_total = sum_money(prices)
    freight_total = sum_money(freights)
    return {
        "item_total_brl": item_total,
        "freight_total_brl": freight_total,
        "reference_order_total_brl": sum_money([item_total, freight_total]),
    }


def reconcile_payments(
    order_id: str,
    payment_rows: List[Dict[str, Any]],
    reference_order_total_brl: Any,
) -> Dict[str, Any]:
    """Build the PaymentFacts payload: totals, count, reconciliation delta and evidence.

    Constructs the PaymentFacts contract output (src/contracts.py).
    """
    payments = sorted(payment_rows, key=lambda r: r["payment_sequential"])
    payment_total = sum_money(row["payment_value_brl"] for row in payments)

    evidence_ids = sorted(
        {f"payment:{order_id}:{row['payment_sequential']}" for row in payments}
    )

    return {
        "order_id": order_id,
        "payments": payments,
        "payment_total_brl": payment_total,
        "payment_count": len(payments),
        "reconciliation_delta_brl": reconciliation_delta(payment_total, reference_order_total_brl),
        "is_reconciled": is_within_tolerance(payment_total, reference_order_total_brl),
        "evidence_ids": evidence_ids,
    }
