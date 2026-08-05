import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from src.contracts import OrderSellerFacts
from src.preflight import run_preflight
from src.tools.order_tools import build_order_repository, evidence_exists, lookup_order_seller_facts


ROOT = Path(__file__).resolve().parents[1]


def _raw_items_by_order() -> dict[str, list[dict[str, str]]]:
    items: dict[str, list[dict[str, str]]] = defaultdict(list)
    with (ROOT / "data" / "olist_order_items_dataset.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            items[row["order_id"]].append(row)
    for rows in items.values():
        rows.sort(key=lambda row: int(row["order_item_id"]))
    return items


def _raw_sellers() -> set[str]:
    with (ROOT / "data" / "olist_sellers_dataset.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        return {row["seller_id"] for row in csv.DictReader(handle)}


def test_tv2_cp4_all_50_order_item_seller_facts_match_raw_csv() -> None:
    cases, _ = run_preflight(ROOT)
    repository = build_order_repository(ROOT)
    raw_items = _raw_items_by_order()
    raw_sellers = _raw_sellers()

    no_item_order_ids: list[str] = []
    total_item_rows = 0
    covered_sellers: set[str] = set()

    for case_id, case in cases.items():
        facts = OrderSellerFacts.model_validate(
            lookup_order_seller_facts(repository, case.claimed_order_id)
        )
        source_items = raw_items.get(case.claimed_order_id, [])
        expected_item_total = sum(
            (Decimal(row["price"]) for row in source_items), Decimal("0.00")
        )
        expected_freight_total = sum(
            (Decimal(row["freight_value"]) for row in source_items), Decimal("0.00")
        )

        assert facts.order_id == case.claimed_order_id, case_id
        assert len(facts.items) == len(source_items), case_id
        assert facts.item_total_brl == expected_item_total, case_id
        assert facts.freight_total_brl == expected_freight_total, case_id
        assert facts.evidence_ids[0] == f"order:{facts.order_id}", case_id
        assert len(facts.evidence_ids) == len(set(facts.evidence_ids)), case_id
        assert len(facts.evidence_ids) <= 10, case_id

        for item, row in zip(facts.items, source_items):
            assert item.order_item_id == int(row["order_item_id"]), case_id
            assert item.seller_id == row["seller_id"], case_id
            assert item.seller_id in raw_sellers, case_id
            assert item.price_brl == Decimal(row["price"]), case_id
            assert item.freight_brl == Decimal(row["freight_value"]), case_id
            covered_sellers.add(item.seller_id)

        if not source_items:
            no_item_order_ids.append(facts.order_id)
            assert facts.items == [], case_id
            assert facts.item_total_brl == Decimal("0.00"), case_id
            assert facts.freight_total_brl == Decimal("0.00"), case_id
            assert not any(evidence_id.startswith("item:") for evidence_id in facts.evidence_ids), case_id
            assert not any(evidence_id.startswith("seller:") for evidence_id in facts.evidence_ids), case_id

        total_item_rows += len(facts.items)

    assert len(cases) == 50
    assert total_item_rows == 48
    assert len(covered_sellers) == 40
    assert len(no_item_order_ids) == 8


def test_tv2_cp4_all_emitted_order_item_seller_evidence_exists() -> None:
    cases, _ = run_preflight(ROOT)
    repository = build_order_repository(ROOT)

    for case_id, case in cases.items():
        facts = lookup_order_seller_facts(repository, case.claimed_order_id)
        for evidence_id in facts.evidence_ids:
            assert not evidence_id.startswith("payment:"), case_id
            assert evidence_exists(repository, evidence_id) is True, f"{case_id}: {evidence_id}"

