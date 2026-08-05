"""Read-only Olist access for order, item, and seller facts.

This module owns TV2 data access. It deliberately avoids payment, delivery
classification, refund, and policy decisions.
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.contracts import ItemFact, OrderSellerFacts


SCHEMA_VERSION = "tv2-order-seller-v1"

REQUIRED_COLUMNS = {
    "olist_orders_dataset.csv": {
        "order_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    },
    "olist_order_items_dataset.csv": {
        "order_id",
        "order_item_id",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
    },
    "olist_sellers_dataset.csv": {
        "seller_id",
        "seller_zip_code_prefix",
        "seller_city",
        "seller_state",
    },
    "olist_order_payments_dataset.csv": {
        "order_id",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    },
}

PROCESSED_TABLE_SCHEMAS = {
    "case_orders": [
        "case_id TEXT PRIMARY KEY",
        "order_id TEXT NOT NULL",
        "source_file TEXT NOT NULL",
    ],
    "orders": [
        "order_id TEXT PRIMARY KEY",
        "order_status TEXT NOT NULL",
        "order_purchase_timestamp TEXT",
        "order_approved_at TEXT",
        "order_delivered_carrier_date TEXT",
        "order_delivered_customer_date TEXT",
        "order_estimated_delivery_date TEXT",
    ],
    "order_items": [
        "order_id TEXT NOT NULL",
        "order_item_id INTEGER NOT NULL",
        "seller_id TEXT NOT NULL",
        "shipping_limit_date TEXT",
        "price_brl TEXT NOT NULL",
        "freight_brl TEXT NOT NULL",
        "PRIMARY KEY (order_id, order_item_id)",
    ],
    "sellers": [
        "seller_id TEXT PRIMARY KEY",
        "seller_zip_code_prefix TEXT",
        "seller_city TEXT",
        "seller_state TEXT",
    ],
    "payments": [
        "order_id TEXT NOT NULL",
        "payment_sequential INTEGER NOT NULL",
        "payment_type TEXT NOT NULL",
        "payment_installments INTEGER NOT NULL",
        "payment_value_brl TEXT NOT NULL",
        "PRIMARY KEY (order_id, payment_sequential)",
    ],
    "order_aggregates": [
        "order_id TEXT PRIMARY KEY",
        "item_total_brl TEXT NOT NULL",
        "freight_total_brl TEXT NOT NULL",
        "payment_total_brl TEXT NOT NULL",
        "payment_count INTEGER NOT NULL",
    ],
}


@dataclass(frozen=True)
class RepositoryManifest:
    schema_version: str
    source_checksums: dict[str, str]
    row_counts: dict[str, int]
    required_columns: dict[str, list[str]]
    processed_table_schemas: dict[str, list[str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_checksums": self.source_checksums,
            "row_counts": self.row_counts,
            "required_columns": self.required_columns,
            "processed_table_schemas": self.processed_table_schemas,
        }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_decimal(value: str | None) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required_columns - fieldnames)
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {missing}")
        return [{key: (value or "") for key, value in row.items()} for row in reader]


class OlistRepository:
    """In-memory read-only index for the TV2 CSV subset."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.orders = {
            row["order_id"]: row
            for row in _read_csv(data_dir / "olist_orders_dataset.csv", REQUIRED_COLUMNS["olist_orders_dataset.csv"])
        }
        items = _read_csv(data_dir / "olist_order_items_dataset.csv", REQUIRED_COLUMNS["olist_order_items_dataset.csv"])
        self.items_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in items:
            self.items_by_order[row["order_id"]].append(row)
        for rows in self.items_by_order.values():
            rows.sort(key=lambda row: int(row["order_item_id"]))
        self.sellers = {
            row["seller_id"]: row
            for row in _read_csv(data_dir / "olist_sellers_dataset.csv", REQUIRED_COLUMNS["olist_sellers_dataset.csv"])
        }
        payments = _read_csv(
            data_dir / "olist_order_payments_dataset.csv",
            REQUIRED_COLUMNS["olist_order_payments_dataset.csv"],
        )
        self.payments_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in payments:
            self.payments_by_order[row["order_id"]].append(row)
        for rows in self.payments_by_order.values():
            rows.sort(key=lambda row: int(row["payment_sequential"]))

    def build_manifest(self) -> RepositoryManifest:
        filenames = sorted(REQUIRED_COLUMNS)
        row_counts = {
            "olist_orders_dataset.csv": len(self.orders),
            "olist_order_items_dataset.csv": sum(len(rows) for rows in self.items_by_order.values()),
            "olist_sellers_dataset.csv": len(self.sellers),
            "olist_order_payments_dataset.csv": sum(len(rows) for rows in self.payments_by_order.values()),
        }
        return RepositoryManifest(
            schema_version=SCHEMA_VERSION,
            source_checksums={name: _sha256(self.data_dir / name) for name in filenames},
            row_counts=row_counts,
            required_columns={name: sorted(columns) for name, columns in REQUIRED_COLUMNS.items()},
            processed_table_schemas=PROCESSED_TABLE_SCHEMAS,
        )

    def get_order_seller_facts(self, order_id: str) -> OrderSellerFacts:
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(f"unknown order_id: {order_id}")

        item_facts: list[ItemFact] = []
        evidence = [f"order:{order_id}"]
        seller_ids: set[str] = set()

        for row in self.items_by_order.get(order_id, []):
            item_id = int(row["order_item_id"])
            seller_id = row["seller_id"]
            item_facts.append(
                ItemFact(
                    order_item_id=item_id,
                    seller_id=seller_id,
                    shipping_limit_date=_parse_timestamp(row["shipping_limit_date"]),
                    price_brl=_parse_decimal(row["price"]),
                    freight_brl=_parse_decimal(row["freight_value"]),
                )
            )
            evidence.append(f"item:{order_id}:{item_id}")
            if seller_id in self.sellers:
                seller_ids.add(seller_id)

        evidence.extend(f"seller:{seller_id}" for seller_id in sorted(seller_ids))
        item_total = sum((item.price_brl for item in item_facts), Decimal("0.00"))
        freight_total = sum((item.freight_brl for item in item_facts), Decimal("0.00"))

        return OrderSellerFacts(
            order_id=order_id,
            order_status=order["order_status"],
            delivered_carrier_at=_parse_timestamp(order["order_delivered_carrier_date"]),
            delivered_customer_at=_parse_timestamp(order["order_delivered_customer_date"]),
            estimated_delivery_at=_parse_timestamp(order["order_estimated_delivery_date"]),
            items=item_facts,
            item_total_brl=item_total,
            freight_total_brl=freight_total,
            evidence_ids=evidence[:10],
        )


class ProcessedOlistRepository:
    """Read-only adapter over the DP-01 SQLite index."""

    def __init__(self, db_path: Path) -> None:
        if not db_path.exists():
            raise FileNotFoundError(f"processed index not found: {db_path}")
        self.db_path = db_path
        self._validate_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _validate_schema(self) -> None:
        with self._connect() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        missing = sorted(set(PROCESSED_TABLE_SCHEMAS) - tables)
        if missing:
            raise ValueError(f"processed index missing tables: {missing}")

    def list_case_order_ids(self) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT case_id, order_id FROM case_orders ORDER BY case_id"
            ).fetchall()
        return {row["case_id"]: row["order_id"] for row in rows}

    def get_order_seller_facts(self, order_id: str) -> OrderSellerFacts:
        with self._connect() as connection:
            order = connection.execute(
                """
                SELECT
                    order_id,
                    order_status,
                    order_delivered_carrier_date,
                    order_delivered_customer_date,
                    order_estimated_delivery_date
                FROM orders
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()
            if order is None:
                raise KeyError(f"unknown order_id: {order_id}")

            items = connection.execute(
                """
                SELECT order_item_id, seller_id, shipping_limit_date, price_brl, freight_brl
                FROM order_items
                WHERE order_id = ?
                ORDER BY order_item_id
                """,
                (order_id,),
            ).fetchall()
            aggregate = connection.execute(
                """
                SELECT item_total_brl, freight_total_brl
                FROM order_aggregates
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()

        item_facts = [
            ItemFact(
                order_item_id=int(row["order_item_id"]),
                seller_id=row["seller_id"],
                shipping_limit_date=_parse_timestamp(row["shipping_limit_date"]),
                price_brl=_parse_decimal(row["price_brl"]),
                freight_brl=_parse_decimal(row["freight_brl"]),
            )
            for row in items
        ]
        seller_ids = sorted({item.seller_id for item in item_facts})
        evidence = [f"order:{order_id}"]
        evidence.extend(f"item:{order_id}:{item.order_item_id}" for item in item_facts)
        evidence.extend(f"seller:{seller_id}" for seller_id in seller_ids)

        item_total = _parse_decimal(aggregate["item_total_brl"]) if aggregate else Decimal("0.00")
        freight_total = _parse_decimal(aggregate["freight_total_brl"]) if aggregate else Decimal("0.00")
        return OrderSellerFacts(
            order_id=order_id,
            order_status=order["order_status"],
            delivered_carrier_at=_parse_timestamp(order["order_delivered_carrier_date"]),
            delivered_customer_at=_parse_timestamp(order["order_delivered_customer_date"]),
            estimated_delivery_at=_parse_timestamp(order["order_estimated_delivery_date"]),
            items=item_facts,
            item_total_brl=item_total,
            freight_total_brl=freight_total,
            evidence_ids=evidence[:10],
        )

    def get_delivery_timeline(self, order_id: str) -> dict[str, str | None]:
        facts = self.get_order_seller_facts(order_id)
        return {
            "order_id": order_id,
            "delivered_carrier_at": _timestamp_to_tool_text(facts.delivered_carrier_at),
            "delivered_customer_at": _timestamp_to_tool_text(facts.delivered_customer_at),
            "estimated_delivery_at": _timestamp_to_tool_text(facts.estimated_delivery_at),
        }

    def get_shipping_limits(self, order_id: str) -> list[dict[str, Any]]:
        facts = self.get_order_seller_facts(order_id)
        return [
            {
                "order_item_id": item.order_item_id,
                "seller_id": item.seller_id,
                "shipping_limit_date": _timestamp_to_tool_text(item.shipping_limit_date),
            }
            for item in facts.items
        ]

    def evidence_exists(self, evidence_id: str) -> bool:
        prefix, *parts = evidence_id.split(":")
        with self._connect() as connection:
            if prefix == "order" and len(parts) == 1:
                return _exists(connection, "SELECT 1 FROM orders WHERE order_id = ?", (parts[0],))
            if prefix == "item" and len(parts) == 2:
                return _exists(
                    connection,
                    "SELECT 1 FROM order_items WHERE order_id = ? AND order_item_id = ?",
                    (parts[0], parts[1]),
                )
            if prefix == "seller" and len(parts) == 1:
                return _exists(connection, "SELECT 1 FROM sellers WHERE seller_id = ?", (parts[0],))
            if prefix == "payment" and len(parts) == 2:
                return _exists(
                    connection,
                    "SELECT 1 FROM payments WHERE order_id = ? AND payment_sequential = ?",
                    (parts[0], parts[1]),
                )
        return False


def _exists(connection: sqlite3.Connection, query: str, params: tuple[str, ...]) -> bool:
    return connection.execute(query, params).fetchone() is not None


def _timestamp_to_tool_text(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ") if value else None
