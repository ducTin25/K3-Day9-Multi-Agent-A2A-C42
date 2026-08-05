from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.audit_outputs import audit_outputs


ORDER_ID = "a" * 32
SELLER_ID = "b" * 32


def _csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    input_dir, data_dir, output_dir = (tmp_path / name for name in ("input", "data", "output"))
    input_dir.mkdir()
    data_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "EC_001.json").write_text(
        json.dumps({"case_id": "EC_001", "customer_request": {"claimed_order_id": ORDER_ID}}),
        encoding="utf-8",
    )
    _csv(
        data_dir / "olist_orders_dataset.csv",
        ["order_id", "order_status", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"],
        [{"order_id": ORDER_ID, "order_status": "delivered", "order_delivered_carrier_date": "2018-01-03 00:00:00", "order_delivered_customer_date": "2018-01-06 00:00:00", "order_estimated_delivery_date": "2018-01-05 00:00:00"}],
    )
    _csv(
        data_dir / "olist_order_items_dataset.csv",
        ["order_id", "order_item_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
        [{"order_id": ORDER_ID, "order_item_id": "1", "seller_id": SELLER_ID, "shipping_limit_date": "2018-01-02 00:00:00", "price": "100.00", "freight_value": "15.00"}],
    )
    _csv(
        data_dir / "olist_order_payments_dataset.csv",
        ["order_id", "payment_sequential", "payment_value"],
        [{"order_id": ORDER_ID, "payment_sequential": "1", "payment_value": "115.00"}],
    )
    _csv(data_dir / "olist_sellers_dataset.csv", ["seller_id"], [{"seller_id": SELLER_ID}])
    return input_dir, data_dir, output_dir


def _good_output() -> dict:
    return {
        "case_id": "EC_001",
        "assessment": {"primary_issue": "late_delivery_seller", "case_status": "action_required", "confidence": 1.0},
        "affected_entities": {"order_ids": [ORDER_ID], "item_ids": [f"{ORDER_ID}:1"], "seller_ids": [SELLER_ID], "payment_ids": [f"{ORDER_ID}:1"]},
        "root_cause_analysis": {"ranked_causes": [{"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1}], "responsible_parties": [{"party_type": "seller", "party_id": SELLER_ID}]},
        "evidence_ids": [f"policy:SELLER_HANDOFF_AFTER_LIMIT", f"order:{ORDER_ID}", f"item:{ORDER_ID}:1", f"payment:{ORDER_ID}:1", f"seller:{SELLER_ID}"],
        "financial_resolution": {"currency": "BRL", "item_total_brl": 100.0, "freight_total_brl": 15.0, "payment_total_brl": 115.0, "recommended_refund_brl": 15.0},
        "resolution_actions": ["refund_freight"],
    }


def test_independent_audit_accepts_raw_csv_grounded_output(tmp_path: Path) -> None:
    input_dir, data_dir, output_dir = _fixture(tmp_path)
    (output_dir / "EC_001.json").write_text(json.dumps(_good_output()), encoding="utf-8")

    report = audit_outputs(input_dir, data_dir, output_dir)

    assert report["proxy_average"] == 100.0
    assert report["finding_counts"] == {}
    assert report["confidence_audit"]["all_identical"] is True


def test_independent_audit_finds_financial_and_evidence_regressions(tmp_path: Path) -> None:
    input_dir, data_dir, output_dir = _fixture(tmp_path)
    output = _good_output()
    output["financial_resolution"]["payment_total_brl"] = 999.0
    output["evidence_ids"].append("seller:not-in-raw-data")
    (output_dir / "EC_001.json").write_text(json.dumps(output), encoding="utf-8")

    report = audit_outputs(input_dir, data_dir, output_dir)

    categories = {finding["category"] for finding in report["cases"][0]["findings"]}
    assert {"financial", "evidence"} <= categories
    assert report["proxy_average"] < 100.0
