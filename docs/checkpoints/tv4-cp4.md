# TV4 — Checkpoint 4 Handoff Report

## Trạng thái
`TV4_READY` — Đã hoàn thành audit và triage toàn bộ 50 case của lượt chạy batch chính thức (`EC_001` đến `EC_050`). 100% case giao hàng được phân loại chính xác, 0 lỗi `undetermined` hoặc `POLICY_UNRESOLVED`.

Không chỉnh sửa `docs/team-plan.md` trực tiếp để tránh xung đột git merge.

## Kết quả Audit 50 Cases (Checkpoint 4)

1. **Phân bố case giao hàng trong 50 output**:
   - `late_delivery_seller`: **8 cases** (`action_required`, hoàn tiền freight từ Seller, có bằng chứng `seller:<id>`, `item:<order_id>:<item_id>`, `policy:SELLER_HANDOFF_AFTER_LIMIT`).
   - `late_delivery_logistics`: **8 cases** (`action_required`, hoàn tiền freight từ Logistics Provider `LOGISTICS_PROVIDER`, có bằng chứng `policy:CARRIER_DELIVERED_AFTER_ESTIMATE`).
   - `unsupported_late_claim`: **9 cases** (`no_action`, hoàn tiền = 0.0 BRL, hành động `reject_late_refund`, có bằng chứng `policy:DELIVERY_WITHIN_ESTIMATE`).
   - Tổng cộng 25 cases liên quan giao hàng / bác bỏ khiếu nại trễ.

2. **Triage & Quality Gate Check**:
   - **0 case `undetermined`**: Tất cả mốc thời gian CSV được parse và so sánh thành công.
   - **100% Khớp bằng chứng (Evidence IDs)**: Toàn bộ evidence IDs có prefix hợp lệ (`order:`, `item:`, `seller:`, `policy:`), không vượt quá 10 IDs.
   - **100% Khớp tài chính**: Toàn bộ case `late_delivery_seller` và `late_delivery_logistics` đều có khoản hoàn bằng đúng tổng cước vận chuyển (`freight_total_brl`).

## Artifacts bổ sung trong Checkpoint 4

- `tests/test_delivery_agent.py`: Bộ test suite audit tự động 50 file trong `output/`.
- `docs/checkpoints/tv4-cp4.md`: Báo cáo Checkpoint 4 của TV4.

## Lệnh kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_delivery_agent.py
.\.venv\Scripts\python.exe -m pytest
```

Kết quả: **123 passed** (100% test suite dự án đều PASS).
