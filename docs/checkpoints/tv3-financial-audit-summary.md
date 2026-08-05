# Financial audit summary (TV3, Checkpoint 5)

Recompute doc lap item_total_brl, freight_total_brl, payment_total_brl va
recommended_refund_brl cho toan bo 50 case that trong `output/`, doi chieu
truc tiep voi `data/*.csv` bang `src/finance.py` + `src/tools/payment_tools.py`
(khong doc lai so co san trong output).

## Outcome

| Metric | Value |
| --- | ---: |
| Cases audited | 50 |
| Cases clean (0 finding) | 50 |
| Cases with findings | 0 |

## Primary issue distribution

| primary_issue | count |
| --- | ---: |
| `canceled_order_paid` | 8 |
| `late_delivery_logistics` | 8 |
| `late_delivery_seller` | 8 |
| `unavailable_order_paid` | 8 |
| `unsupported_late_claim` | 9 |
| `valid_split_payment` | 9 |

## Findings

| case_id | order_id | findings |
| --- | --- | --- |
| _none_ | - | - |

## Checks performed per case

1. `item_total_brl` / `freight_total_brl` == sum of `olist_order_items_dataset.csv` rows for the order.
2. `payment_total_brl` == sum of `olist_order_payments_dataset.csv` rows (never multiplied by `payment_installments`).
3. `recommended_refund_brl` matches its EC_POLICY_V1 source (`payment_total_brl` / `freight_total_brl` / `0.00`) for the case's `primary_issue`.
4. `valid_split_payment` / `unsupported_late_claim`: `|payment_total - (item_total+freight_total)| <= 0.10 BRL`.
5. All four money fields are 2-decimal, `ROUND_HALF_UP`.
6. Every `payment:<order_id>:<seq>` evidence ID in the output is backed by a real payment row.

## Go/no-go for financial fields

**GO** - 0 findings across 50/50 cases.
