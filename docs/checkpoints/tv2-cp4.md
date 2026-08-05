# TV2 Checkpoint 4 - 50-Case Order/Seller Triage

## Scope

TV2 CP4 covers the `ORDER_*`, `ITEM_*`, and `SELLER_*` failure groups for the full 50-case set.

It verifies:

- all 50 validated `case_id` values have a lookupable `claimed_order_id`;
- every `OrderSellerFacts.order_id` matches the case input;
- item rows are sorted and preserve source `order_item_id`;
- item totals and freight totals match raw CSV Decimal sums;
- `order:`, `item:`, and `seller:` evidence IDs exist in the processed index;
- unavailable/no-item orders return empty `items`, no seller evidence, and zero item/freight totals.

Payment totals, refund calculations, final policy decisions, and output writing remain outside TV2 ownership.

## Result

The TV2 audit covers all 50 official cases:

- `50` cases received by preflight
- `50` order IDs matched in the processed index
- `48` item rows covered by the 50 orders
- `40` unique seller rows covered by the 50 orders
- `8` no-item orders handled explicitly
- `0` order/item/seller evidence mismatches

## Verification

```powershell
python -m pytest tests\test_tv2_checkpoint4.py tests\test_repository.py tests\test_order_seller_agent.py
```

