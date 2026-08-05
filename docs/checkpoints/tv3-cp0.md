# TV3 — Checkpoint 0 handoff (Payment fixtures)

## Trạng thái

`READY` — fixtures cho Payment domain đã có, quy tắc Decimal/tolerance đã được xác nhận bằng test tự động. `src/tools/payment_tools.py` (Payment Agent thật) **chưa tồn tại** — đây là việc của Checkpoint 1, không nằm trong phạm vi CP0 này.

## Artifact sở hữu

- `tests/fixtures/payment/*.json` — 7 fixture: `single`, `split`, `zero`, `mismatch`, `boundary_delta_0_09`, `boundary_delta_0_10`, `boundary_delta_0_11`.
- `tests/test_payment_fixtures.py` — xác nhận fixture khớp contract `PaymentFacts` (`src/contracts.py`) và đúng quy tắc Decimal/tolerance (không phụ thuộc `payment_tools.py`).
- `docs/checkpoints/tv3-cp0.md` — tài liệu này.

## Quy tắc đã xác nhận

1. **Không nhân theo installments**: `payment_value_brl` là tổng tiền của *cả payment row*, không phải giá trị từng kỳ trả góp (README mục 2). `payment_total_brl = sum(payment_value_brl)`, tuyệt đối không nhân với `payment_installments`.
   - Bằng chứng: fixture `single` (1 row, 8 installments) và `split` (row 2 có 3 installments) — nếu code nhân nhầm, `split` sẽ ra 350.00 thay vì 150.00 đúng.
2. **Tolerance đối soát = 0.10 BRL, inclusive**: `is_reconciled = (|payment_total_brl - reference_order_total_brl| <= 0.10)`. Hằng số khớp `PAYMENT_TOLERANCE = Decimal("0.10")` trong `src/tools/policy_tools.py`.
3. **Decimal, không dùng float**: mọi giá trị tiền parse qua `Decimal(str(x))`, làm tròn 2 chữ số thập phân `ROUND_HALF_UP` (khớp `MONEY_QUANTUM` trong `policy_tools.py`).
4. **Zero payment**: khi không có payment row nào, `payment_total_brl = 0.00`, `payment_count = 0`, `evidence_ids = []` (không được bịa evidence id không dựng được từ dữ liệu — README mục 5).

## Bảng test biên (delta = |payment_total_brl - reference_order_total_brl|)

| Fixture | payment_total_brl | reference_order_total_brl | delta | So với ngưỡng 0.10 | is_reconciled |
| --- | ---: | ---: | ---: | --- | :---: |
| `boundary_delta_0_09` | 99.91 | 100.00 | **0.09** | < 0.10 | `true` |
| `boundary_delta_0_10` | 99.90 | 100.00 | **0.10** | = 0.10 (biên) | `true` |
| `boundary_delta_0_11` | 99.89 | 100.00 | **0.11** | > 0.10 | `false` |
| `single` | 115.00 | 115.00 | 0.00 | trong ngưỡng | `true` |
| `split` | 150.00 | 150.00 | 0.00 | trong ngưỡng | `true` |
| `zero` | 0.00 | 0.00 | 0.00 | trong ngưỡng | `true` |
| `mismatch` | 120.00 | 200.00 | 80.00 | vượt xa ngưỡng | `false` |

Case quan trọng nhất là `boundary_delta_0_10`: xác nhận ngưỡng là `<=` (inclusive) chứ không phải `<`. Nếu ai đó implement Payment Agent dùng so sánh `< 0.10` thay vì `<= 0.10`, case này sẽ fail.

## Cách kiểm tra

```powershell
.venv\Scripts\python.exe -m pytest tests/test_payment_fixtures.py -v
```

Kết quả tại checkpoint: 6 test / 35 subtest pass. Toàn bộ suite (`pytest -q`): 32 passed.

## Lưu ý tích hợp cho ai làm Payment Agent / Policy ở CP1

- `PaymentFacts` (contract, `src/contracts.py`) dùng field `is_reconciled`, nhưng `src/tools/policy_tools.py::_evaluate` lại đọc `payment.get("is_reconciled_within_0_10")` từ `InvestigationBundle` — **hai tên field khác nhau**. Người ghép `PaymentFacts` vào `InvestigationBundle.payment` cần map `is_reconciled -> is_reconciled_within_0_10` (hoặc đổi tên field cho khớp), nếu không policy sẽ luôn coi `reconciled=False` mặc định.
- `PaymentFacts` không tự chứa `reference_order_total_brl` (tổng item + freight) — giá trị này đến từ `OrderSellerFacts.item_total_brl + freight_total_brl`. Payment Agent cần nhận giá trị này làm input để tính `reconciliation_delta_brl`, nó không tự suy ra được chỉ từ CSV payments.
