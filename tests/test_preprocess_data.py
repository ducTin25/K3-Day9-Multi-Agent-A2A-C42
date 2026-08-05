import json
import sqlite3
from pathlib import Path

from src.contracts import OrderSellerFacts
from src.preflight import run_preflight
from scripts.preprocess_data import run_preprocess


ROOT = Path(__file__).resolve().parents[1]
ORDER_SELLER_FIXTURES = ROOT / "tests" / "fixtures" / "order_seller"


def test_preprocess_manifest_and_sqlite_index_include_50_orders(tmp_path: Path) -> None:
    manifest = run_preprocess(ROOT, tmp_path)
    db_path = tmp_path / "olist_case_index.sqlite"

    assert manifest["valid"] is True
    assert manifest["case_count"] == 50
    assert manifest["unique_order_count"] == 50
    assert manifest["matched_order_count"] == 50
    assert manifest["processed_row_counts"]["case_orders"] == 50
    assert manifest["processed_row_counts"]["orders"] == 50
    assert db_path.exists()
    assert (tmp_path / "manifest.json").exists()

    with sqlite3.connect(db_path) as connection:
        case_count = connection.execute("SELECT COUNT(*) FROM case_orders").fetchone()[0]
        order_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        payment_count = connection.execute("SELECT COUNT(*) FROM payments").fetchone()[0]

    assert case_count == 50
    assert order_count == 50
    assert payment_count == manifest["processed_row_counts"]["payments"]


def test_order_seller_fixtures_parse_and_reference_existing_case_orders() -> None:
    cases, _ = run_preflight(ROOT)
    fixture_paths = sorted(ORDER_SELLER_FIXTURES.glob("*.json"))

    assert {path.stem for path in fixture_paths} == {
        "canceled_order",
        "delivered_ec004",
        "delivered_multi_item",
        "delivered_single_item",
        "unavailable_no_item",
    }

    for path in fixture_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        facts = OrderSellerFacts.model_validate(payload["facts"])
        assert payload["case_id"] in cases
        assert facts.order_id == cases[payload["case_id"]].claimed_order_id
        assert f"order:{facts.order_id}" in facts.evidence_ids

