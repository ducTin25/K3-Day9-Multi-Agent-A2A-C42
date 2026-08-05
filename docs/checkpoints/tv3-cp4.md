# TV3 — Checkpoint 4 handoff (PAYMENT_*/FINANCIAL_* triage)

## Trạng thái

`READY — 0 mismatch` — TV1 đã chạy batch 50 case thật (live OpenAI, `docs/checkpoints/tv1-cp4.md`), `output/EC_001.json..EC_050.json` đã tồn tại. Tôi recompute độc lập toàn bộ 50 case theo đúng phạm vi CP4 (`PAYMENT_*, FINANCIAL_*, tolerance/rounding`) và **không tìm thấy mismatch nào** — không có gì phải sửa ở `payment`/`finance` tại thời điểm audit.

## Artifact sở hữu

- `tests/test_cp4_financial_recompute.py` — 7 test, chạy trên **tất cả 50 file `output/EC_*.json` thật** (không phải fixture/mẫu), mỗi test recompute độc lập bằng `src/finance.py` + `src/tools/payment_tools.py` (đọc thẳng CSV, không tin số trong output):
  1. Đủ 50/50 file, đúng `case_id`.
  2. `item_total_brl` / `freight_total_brl` khớp tổng thật từ `olist_order_items_dataset.csv`.
  3. `payment_total_brl` khớp tổng thật từ `olist_order_payments_dataset.csv`, xác nhận không nơi nào nhân theo `payment_installments`.
  4. `recommended_refund_brl` đúng nguồn theo `primary_issue` (payment_total cho canceled/unavailable, freight_total cho late_delivery_*, 0 cho valid_split_payment/unsupported_late_claim).
  5. `valid_split_payment` / `unsupported_late_claim`: `|payment_total - (item_total+freight_total)| <= 0.10 BRL`.
  6. Mọi field tiền đã làm tròn đúng 2 chữ số (`ROUND_HALF_UP`).
  7. Evidence `payment:<order_id>:<seq>` trong output chỉ trỏ tới payment row có thật.
- `docs/checkpoints/tv3-cp4.md` — tài liệu này.

## Kết quả

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cp4_financial_recompute.py -v
```

**7/7 pass trên cả 50/50 case** (~43s). Full suite `pytest -q`: **125 passed**, không có failure.

Đối chiếu chéo với `logging/run_summary.json` (TV1): không có bất kỳ error code nào được ghi nhận (0 failed đúng như TV1 báo cáo) — audit độc lập của tôi xác nhận lại bằng số liệu tự tính, không chỉ tin vào self-report của pipeline.

## Điều kiện hoàn tất CP4 của TV3 ("Không còn mismatch payment/refund")

**Đã đạt** ngay từ lần audit đầu tiên trên live run — không cần vòng sửa lỗi nào. Không có case nào bị route `FINANCIAL_TOTAL_MISMATCH`/`FINANCIAL_REFUND_MISMATCH` về `payment_agent` trong run này.

Lý do không có lỗi: `payment_agent` (CP2 của tôi) tự đọc thẳng CSV bằng `src/finance.py`/`src/tools/payment_tools.py`, cùng nguồn dữ liệu và cùng logic Decimal/tolerance đã audit khớp với TV5 ở CP3 (`docs/checkpoints/tv3-cp3.md`) — nên khi chạy thật, không phát sinh sai lệch mới.

## Việc còn lại (không phải PAYMENT_*/FINANCIAL_*, không thuộc phạm vi CP4 của tôi)

Rủi ro cấu trúc đã ghi ở CP3 (`item_total_brl`/`freight_total_brl` tính độc lập 2 nơi — TV2 và TV3, chưa dùng chung hàm) **vẫn còn**, nhưng qua audit 50 case thật lần này vẫn chưa gây sai lệch số liệu nào — giữ nguyên khuyến nghị cũ, không chặn CP4.
