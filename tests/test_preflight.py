from pathlib import Path

from src.preflight import run_preflight


ROOT = Path(__file__).resolve().parents[1]


def test_preflight_normalizes_all_50_cases() -> None:
    cases, report = run_preflight(ROOT)
    assert report["valid"] is True
    assert report["case_count"] == 50
    assert list(cases) == [f"EC_{index:03d}" for index in range(1, 51)]
    ec050 = next(row for row in report["normalized_sources"] if row["case_id"] == "EC_050")
    assert ec050["source_file"] == "download"
    assert ec050["canonical_file"] == "EC_050.json"

