"""DP-01 preprocessing for the 50 Olist dispute cases.

The script validates raw CSV headers, parses IDs/timestamps/money fields,
filters rows for the 50 input order IDs, and writes a read-only processed
SQLite index plus a manifest. It does not classify issues or decide refunds.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.olist_repository import OlistRepository, PROCESSED_TABLE_SCHEMAS, SCHEMA_VERSION
from src.preflight import run_preflight


DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed"


def _timestamp_to_text(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ") if value else None


def _decimal_to_text(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _payment_total(rows: list[dict[str, str]]) -> Decimal:
    return sum((Decimal(row["payment_value"]) for row in rows), Decimal("0.00"))


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _quality_issues(repository: OlistRepository, order_ids: list[str]) -> dict[str, Any]:
    unique_order_ids = set(order_ids)
    seller_ids = {
        item["seller_id"]
        for order_id in unique_order_ids
        for item in repository.items_by_order.get(order_id, [])
    }
    return {
        "missing_order_ids": sorted(unique_order_ids - set(repository.orders)),
        "orders_without_items": sorted(
            order_id for order_id in unique_order_ids if not repository.items_by_order.get(order_id)
        ),
        "orders_without_payments": sorted(
            order_id for order_id in unique_order_ids if not repository.payments_by_order.get(order_id)
        ),
        "missing_seller_ids": sorted(seller_ids - set(repository.sellers)),
        "duplicate_case_order_ids": sorted(
            order_id
            for order_id, count in Counter(order_ids).items()
            if count > 1
        ),
    }


def _write_sqlite(
    db_path: Path,
    cases_by_id: dict[str, Any],
    source_by_case: dict[str, str],
    repository: OlistRepository,
) -> None:
    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for table, columns in PROCESSED_TABLE_SCHEMAS.items():
            connection.execute(f"CREATE TABLE {table} ({', '.join(columns)})")

        order_ids = {case.claimed_order_id for case in cases_by_id.values()}

        for case_id, case in sorted(cases_by_id.items()):
            connection.execute(
                "INSERT INTO case_orders (case_id, order_id, source_file) VALUES (?, ?, ?)",
                (case_id, case.claimed_order_id, source_by_case[case_id]),
            )

        for order_id in sorted(order_ids):
            order = repository.orders[order_id]
            connection.execute(
                """
                INSERT INTO orders (
                    order_id,
                    order_status,
                    order_purchase_timestamp,
                    order_approved_at,
                    order_delivered_carrier_date,
                    order_delivered_customer_date,
                    order_estimated_delivery_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    order["order_status"],
                    order["order_purchase_timestamp"] or None,
                    order["order_approved_at"] or None,
                    order["order_delivered_carrier_date"] or None,
                    order["order_delivered_customer_date"] or None,
                    order["order_estimated_delivery_date"] or None,
                ),
            )

            facts = repository.get_order_seller_facts(order_id)
            for item in facts.items:
                connection.execute(
                    """
                    INSERT INTO order_items (
                        order_id,
                        order_item_id,
                        seller_id,
                        shipping_limit_date,
                        price_brl,
                        freight_brl
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        item.order_item_id,
                        item.seller_id,
                        _timestamp_to_text(item.shipping_limit_date),
                        _decimal_to_text(item.price_brl),
                        _decimal_to_text(item.freight_brl),
                    ),
                )

            for payment in repository.payments_by_order.get(order_id, []):
                connection.execute(
                    """
                    INSERT INTO payments (
                        order_id,
                        payment_sequential,
                        payment_type,
                        payment_installments,
                        payment_value_brl
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        int(payment["payment_sequential"]),
                        payment["payment_type"],
                        int(payment["payment_installments"]),
                        _decimal_to_text(Decimal(payment["payment_value"])),
                    ),
                )

            for item in facts.items:
                if item.seller_id in repository.sellers:
                    seller = repository.sellers[item.seller_id]
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO sellers (
                            seller_id,
                            seller_zip_code_prefix,
                            seller_city,
                            seller_state
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            item.seller_id,
                            seller["seller_zip_code_prefix"],
                            seller["seller_city"],
                            seller["seller_state"],
                        ),
                    )

            payments = repository.payments_by_order.get(order_id, [])
            connection.execute(
                """
                INSERT INTO order_aggregates (
                    order_id,
                    item_total_brl,
                    freight_total_brl,
                    payment_total_brl,
                    payment_count
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    _decimal_to_text(facts.item_total_brl),
                    _decimal_to_text(facts.freight_total_brl),
                    _decimal_to_text(_payment_total(payments)),
                    len(payments),
                ),
            )


def run_preprocess(root: Path = ROOT, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    cases_by_id, preflight_report = run_preflight(root)
    repository = OlistRepository(root / "data")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_by_case = {
        row["case_id"]: row["source_file"]
        for row in preflight_report["normalized_sources"]
    }
    db_path = output_dir / "olist_case_index.sqlite"
    _write_sqlite(db_path, cases_by_id, source_by_case, repository)

    case_order_ids = [case.claimed_order_id for case in cases_by_id.values()]
    order_ids = set(case_order_ids)
    quality = _quality_issues(repository, case_order_ids)
    manifest = repository.build_manifest().as_dict()
    manifest.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "processed_database": _display_path(db_path, root),
            "case_count": len(cases_by_id),
            "unique_order_count": len(order_ids),
            "case_ids": sorted(cases_by_id),
            "order_ids": sorted(order_ids),
            "matched_order_count": len(order_ids - set(quality["missing_order_ids"])),
            "processed_row_counts": _processed_row_counts(db_path),
            "quality_issues": quality,
            "valid": (
                len(cases_by_id) == 50
                and len(order_ids) == 50
                and not quality["missing_order_ids"]
                and not quality["missing_seller_ids"]
            ),
        }
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not manifest["valid"]:
        raise ValueError(json.dumps(manifest["quality_issues"], ensure_ascii=False, indent=2))
    return manifest


def _processed_row_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in PROCESSED_TABLE_SCHEMAS
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else root / "data" / "processed"
    manifest = run_preprocess(root, output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
