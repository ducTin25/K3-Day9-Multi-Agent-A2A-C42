# TV3 — Checkpoint 1 handoff (Payment tools + finance helpers)

## Trạng thái

`READY` — Payment tools và Decimal finance helpers đã có, test pass bằng cả fixture CP0 lẫn dữ liệu CSV thật. `src/agents/payment.py` (PaymentAgent thật + prompt) là việc của Checkpoint 2, chưa làm ở đây.

## Artifact sở hữu

- `src/finance.py` — `to_money`, `sum_money`, `reconciliation_delta`, `is_within_tolerance` (`PAYMENT_TOLERANCE = Decimal("0.10")`, `MONEY_QUANTUM = Decimal("0.01")`, `ROUND_HALF_UP`).
- `src/tools/payment_tools.py`:
  - `get_order_payments(order_id)` — đọc `olist_order_payments_dataset.csv`, trả list payment row (không nhân `payment_installments`).
  - `get_order_financial_reference(order_id)` — đọc `olist_order_items_dataset.csv`, trả `item_total_brl` + `freight_total_brl` + `reference_order_total_brl`.
  - `reconcile_payments(order_id, payment_rows, reference_order_total_brl)` — dựng payload đúng contract `PaymentFacts` (`src/contracts.py`): `payments`, `payment_total_brl`, `payment_count`, `reconciliation_delta_brl`, `is_reconciled`, `evidence_ids`.
- `tests/test_finance.py` — 10 test cho Decimal parsing, sum, tolerance boundary.
- `tests/test_payment.py` — 10 test: 7 test chạy `reconcile_payments` qua đúng 7 fixture CP0 (`tests/fixtures/payment/`), 3 test integration bằng dữ liệu CSV thật.

## Tự kiểm tra (đúng yêu cầu CP1: "Test sum row, split payment và tolerance pass")

- **Sum row**: `test_finance.py::TestSumMoney` + `test_payment.py::test_sum_single_payment_row_matches_real_order` — dùng order thật `b81ef226f3fe1789b1e8b2acac839d17` (1 item 79.80 + freight 19.53 = 99.33, payment 99.33 → khớp tuyệt đối, `is_reconciled=true`).
- **Split payment**: `test_payment.py::test_split_payment_matches_real_order` — order thật `0016dfedd97fc2950e388d2971d718c7` (item 49.75 + freight 20.80 = 70.55; 2 payment row 17.92 + 52.63 = 70.55 → `payment_count=2`, reconciled).
- **Tolerance**: `test_finance.py::TestReconciliationTolerance` + `test_payment.py::test_boundary_0_09/0_10/0_11_fixture` — xác nhận ngưỡng `<= 0.10` inclusive bằng cả helper thuần và tool thật.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_finance.py tests/test_payment.py -v
```

Kết quả: 20/20 pass. Full suite `pytest -q`: **51 passed, 1 unrelated failure** (xem mục dưới).

## Lỗi phát hiện — KHÔNG thuộc phạm vi TV3

`tests/test_preflight.py::test_preflight_normalizes_all_50_cases` fail, đã tồn tại **trước** khi tôi thêm code CP1, không liên quan `finance.py`/`payment_tools.py`:

```
assert ec050["source_file"] == "download"
AssertionError: assert 'EC_050.json' == 'download'
```

Nguyên nhân: test hardcode kỳ vọng cũ theo team-plan.md dòng 29 ("payload EC_050 nằm trong file không đuôi `input/download`"), nhưng `input/` hiện đã có sẵn `EC_050.json` đúng tên (dữ liệu đã được fix ở một commit sau). Test của TV1 chưa cập nhật theo dữ liệu mới. File này thuộc ownership TV1 (`src/config/agents.*`, preflight) nên tôi không tự sửa — báo để TV1 xử lý.

## Việc chuyển sang Checkpoint 2

- `src/agents/payment.py` sẽ gọi `get_order_payments` + `get_order_financial_reference` + `reconcile_payments` từ `payment_tools.py`, bọc thêm prompt/model config, rồi trả đúng `PaymentFacts` qua `HandoffEnvelope`.
- Nhắc lại lưu ý từ CP0: `PaymentFacts.is_reconciled` (contract) khác tên với `is_reconciled_within_0_10` mà `policy_tools.py` đang đọc từ `InvestigationBundle.payment` — người ghép bundle ở CP2/CP3 cần map lại tên field.
