# TV2 Checkpoint 0 - Data Access and Order/Seller

## Published contract

TV2 publishes the order/item/seller data contract in `src/data/olist_repository.py`:

- `REQUIRED_COLUMNS`: raw CSV headers required by the TV2 layer.
- `PROCESSED_TABLE_SCHEMAS`: proposed read-only processed index schema.
- `SCHEMA_VERSION`: `tv2-order-seller-v1`.

The TV2 layer only reads:

- `data/olist_orders_dataset.csv`
- `data/olist_order_items_dataset.csv`
- `data/olist_sellers_dataset.csv`

It does not read payment, geolocation, review, product, or policy data.

## Tool handoff

`src/tools/order_tools.py` exposes deterministic functions for the future `OrderSellerAgent`:

- `build_order_repository(root)`
- `lookup_order_seller_facts(repository, order_id)`
- `describe_order_seller_schema(repository)`

`lookup_order_seller_facts` returns the shared `OrderSellerFacts` contract from `src/contracts.py`.

## Fixture

The initial TV2 fixture is:

- `tests/fixtures/tv2_order_seller_fixture.json`

## Verification

Checkpoint 0 verification:

```powershell
python -m pytest tests\test_preflight.py tests\test_repository.py
```

Full current repo verification:

```powershell
python -m pytest
```

## Checkpoint 1 update

TV2 now has a deterministic processed-index adapter:

- `ProcessedOlistRepository` reads `data/processed/olist_case_index.sqlite` in read-only mode.
- `build_order_repository(root)` prefers the processed SQLite index when it exists and falls back to raw CSV for regeneration.
- `lookup_order_seller_facts` works against both raw and processed repositories.
- `list_case_order_ids` confirms the 50 validated case-to-order mappings from DP-01.
- `evidence_exists` verifies `order:`, `item:`, `seller:`, and `payment:` evidence IDs against the processed index.

Checkpoint 1 verification:

```powershell
python -m pytest tests\test_repository.py tests\test_preprocess_data.py
```
