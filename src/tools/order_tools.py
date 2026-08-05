"""Order/Seller tool functions exposed to OrderSellerAgent."""

from __future__ import annotations

from pathlib import Path

from src.contracts import OrderSellerFacts
from src.data.olist_repository import OlistRepository, ProcessedOlistRepository, RepositoryManifest


def build_order_repository(root: Path) -> OlistRepository | ProcessedOlistRepository:
    processed = root / "data" / "processed" / "olist_case_index.sqlite"
    if processed.exists():
        return ProcessedOlistRepository(processed)
    return OlistRepository(root / "data")


def lookup_order_seller_facts(
    repository: OlistRepository | ProcessedOlistRepository,
    order_id: str,
) -> OrderSellerFacts:
    return repository.get_order_seller_facts(order_id)


def describe_order_seller_schema(repository: OlistRepository | ProcessedOlistRepository) -> RepositoryManifest:
    if isinstance(repository, ProcessedOlistRepository):
        return OlistRepository(repository.db_path.parents[1]).build_manifest()
    return repository.build_manifest()


def list_case_order_ids(repository: ProcessedOlistRepository) -> dict[str, str]:
    return repository.list_case_order_ids()


def evidence_exists(repository: ProcessedOlistRepository, evidence_id: str) -> bool:
    return repository.evidence_exists(evidence_id)

