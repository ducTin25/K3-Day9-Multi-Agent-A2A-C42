from decimal import Decimal
from pathlib import Path

from src.preflight import run_preflight
from src.data.olist_repository import OlistRepository, ProcessedOlistRepository
from src.tools.order_tools import (
    build_order_repository,
    describe_order_seller_schema,
    evidence_exists,
    list_case_order_ids,
    lookup_order_seller_facts,
)


ROOT = Path(__file__).resolve().parents[1]


def test_tv2_schema_manifest_publishes_required_tables_and_columns() -> None:
    repository = build_order_repository(ROOT)
    manifest = describe_order_seller_schema(repository).as_dict()

    assert manifest["schema_version"] == "tv2-order-seller-v1"
    assert set(manifest["required_columns"]) == {
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_order_payments_dataset.csv",
        "olist_sellers_dataset.csv",
    }
    assert "orders" in manifest["processed_table_schemas"]
    assert "order_items" in manifest["processed_table_schemas"]
    assert "sellers" in manifest["processed_table_schemas"]


def test_order_seller_lookup_returns_contract_facts_for_first_case() -> None:
    cases, _ = run_preflight(ROOT)
    repository = build_order_repository(ROOT)

    facts = lookup_order_seller_facts(repository, cases["EC_001"].claimed_order_id)

    assert facts.order_id == cases["EC_001"].claimed_order_id
    assert facts.order_status
    assert facts.item_total_brl >= Decimal("0.00")
    assert facts.freight_total_brl >= Decimal("0.00")
    assert f"order:{facts.order_id}" in facts.evidence_ids
    for item in facts.items:
        assert f"item:{facts.order_id}:{item.order_item_id}" in facts.evidence_ids
        assert item.price_brl >= Decimal("0.00")
        assert item.freight_brl >= Decimal("0.00")


def test_all_preflight_cases_are_lookupable_by_tv2_repository() -> None:
    cases, _ = run_preflight(ROOT)
    repository = build_order_repository(ROOT)

    facts_by_case = {
        case_id: lookup_order_seller_facts(repository, case.claimed_order_id)
        for case_id, case in cases.items()
    }

    assert len(facts_by_case) == 50
    assert all(facts.order_id for facts in facts_by_case.values())


def test_order_repository_prefers_processed_index_when_available() -> None:
    repository = build_order_repository(ROOT)

    assert isinstance(repository, ProcessedOlistRepository)
    case_order_ids = list_case_order_ids(repository)
    assert len(case_order_ids) == 50
    assert case_order_ids["EC_004"] == "fd28a6dfe413804d0b89b7c9abf5b1f3"


def test_processed_repository_supports_evidence_lookup_and_no_item_case() -> None:
    repository = build_order_repository(ROOT)
    assert isinstance(repository, ProcessedOlistRepository)

    no_item = lookup_order_seller_facts(repository, "9a31fd9d697e9670777501f720773fd9")

    assert no_item.order_status == "unavailable"
    assert no_item.items == []
    assert no_item.item_total_brl == Decimal("0.00")
    assert no_item.freight_total_brl == Decimal("0.00")
    assert evidence_exists(repository, f"order:{no_item.order_id}") is True
    assert evidence_exists(repository, f"item:{no_item.order_id}:1") is False


def test_raw_repository_remains_available_for_regenerating_processed_index() -> None:
    repository = OlistRepository(ROOT / "data")

    facts = lookup_order_seller_facts(repository, "8067c5e4834f3c0a3c8a4e921d65c5b1")

    assert len(facts.items) == 2
    assert facts.item_total_brl == Decimal("163.98")
    assert facts.freight_total_brl == Decimal("16.64")
