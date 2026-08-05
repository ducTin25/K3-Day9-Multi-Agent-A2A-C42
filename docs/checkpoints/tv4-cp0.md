# TV4 — Checkpoint 0 Handoff Report (Delivery Fixtures)

## Trạng thái

`READY` — Đã hoàn thành xây dựng 4 bộ dữ liệu kiểm thử giả lập (synthetic fixtures) cho miền Giao hàng (Delivery domain). Tất cả fixtures đã được xác nhận khớp 100% với Pydantic contract `DeliveryFacts` (`src/contracts.py`). `src/tools/delivery_tools.py` chưa được xây dựng ở CP0 này (đây là nhiệm vụ của CP1).

Không chỉnh sửa `docs/team-plan.md` trực tiếp để tránh xung đột git merge.

## Artifacts sở hữu

- `tests/fixtures/delivery/on_time.json` — Case giao hàng đúng hạn (`is_late=false`, `late_stage="not_late"`).
- `tests/fixtures/delivery/seller_late.json` — Case Seller bàn giao kho trễ (`is_late=true`, `late_stage="seller"`, chứa `violating_seller_ids`).
- `tests/fixtures/delivery/logistics_late.json` — Case Đơn vị vận chuyển giao tới khách trễ (`is_late=true`, `late_stage="logistics"`).
- `tests/fixtures/delivery/missing_timestamp.json` — Case thiếu mốc thời gian ISO (`is_late=false`, `late_stage="undetermined"`, phát tín hiệu `warnings`).
- `docs/checkpoints/tv4-cp0.md` — Báo cáo Checkpoint 0 của TV4.

## Quy tắc Giao hàng đã xác nhận (Delivery Boundary Rules)

1. **Giao đúng hạn (`not_late`)**: `delivered_customer_at <= estimated_delivery_at`. `late_stage = "not_late"`, `violating_seller_ids = []`.
2. **Seller bàn giao trễ (`seller`)**: `delivered_carrier_at > shipping_limit_date`. `late_stage = "seller"`, `violating_seller_ids` liệt kê danh sách Seller ID vi phạm hạn bàn giao.
3. **Đơn vị vận chuyển trễ (`logistics`)**: `delivered_carrier_at <= shipping_limit_date` nhưng `delivered_customer_at > estimated_delivery_at`. `late_stage = "logistics"`, `violating_seller_ids = []`.
4. **Thiếu dữ liệu thời gian (`undetermined`)**: Trường hợp thiếu mốc `delivered_customer_at` hoặc `estimated_delivery_at` $\rightarrow$ `late_stage = "undetermined"`, ghi nhận `warnings`.
5. **Ràng buộc Evidence IDs**: Tất cả evidence IDs tuân theo tiền tố chuẩn (`order:`, `item:`, `seller:`), tổng số lượng evidence IDs không vượt quá 10.

## Bảng Đối soát Fixtures CP0

| Fixture File | order_id | is_late | late_stage | violating_seller_ids | Bằng chứng kiểm tra |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `on_time.json` | `e2a03ccf5ea816036608b2d8c3ab8e60` | `false` | `not_late` | `[]` | `delivered_customer_at` < `estimated_delivery_at` |
| `seller_late.json` | `8067c5e4834f3c0a3c8a4e921d65c5b1` | `true` | `seller` | `["sel_late_123"]` | `delivered_carrier_at` > `shipping_limit_date` |
| `logistics_late.json` | `9a31fd9d697e9670777501f720773fd9` | `true` | `logistics` | `[]` | Carrier đúng hạn nhưng Customer trễ |
| `missing_timestamp.json` | `f3769c3a6e036e52296e00b8c6a51d8b` | `false` | `undetermined` | `[]` | Thiếu `delivered_customer_at` |

## Lệnh kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_delivery_agent.py -v
```
