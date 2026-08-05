# TV2 Checkpoint 3 - Integration Audit

## Scope

TV2 owns the Order/Seller slice during integration:

- affected order IDs
- affected item IDs
- affected seller IDs
- order/item/seller evidence IDs
- no-item behavior for unavailable/canceled orders

TV2 does not own payment totals, refund decisions, policy priority, or final output writing.

## Runtime integration

`build_hybrid_handlers` now routes `order_seller_agent` to the real `OrderSellerAgent` instead of the TV1 stub. The hybrid runtime still keeps TV3 payment as a stub until that workstream is integrated.

## Representative cases audited

| Case | Order status | Shape | TV2 focus |
| --- | --- | --- | --- |
| `EC_001` | delivered | single item | base order/item/seller evidence |
| `EC_002` | delivered | multi-item | stable item IDs and total aggregation |
| `EC_003` | canceled | single item | canceled order still exposes item/seller rows |
| `EC_004` | delivered | single item | user-referenced case, delivered before estimate |
| `EC_005` | unavailable | no item | empty item/seller sets and zero item/freight totals |
| `EC_025` | delivered | three items | larger multi-item aggregation |

## Verification

```powershell
python -m pytest tests\test_tv2_checkpoint3.py tests\test_order_seller_agent.py tests\test_repository.py
```

