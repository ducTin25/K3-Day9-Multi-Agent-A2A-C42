# TV4 — Checkpoint 1 Handoff Report (Delivery Tools & Timestamp Comparator)

## Trạng thái

`READY` — Đã hoàn thành bộ công cụ `src/tools/delivery_tools.py` để trích xuất mốc thời gian vận chuyển từ dữ liệu CSV Olist và thuật toán so sánh `compare_delivery_timestamps`. Đã kiểm thử qua toàn bộ fixtures CP0 cũng như dữ liệu CSV thực tế.

Không chỉnh sửa `docs/team-plan.md` trực tiếp để tránh xung đột git merge.

## Artifacts sở hữu

- `src/tools/delivery_tools.py`:
  - `get_delivery_timeline(order_id)` — Đọc `olist_orders_dataset.csv`, trả mốc thời gian ISO (`delivered_customer_at`, `estimated_delivery_at`, `delivered_carrier_at`).
  - `get_shipping_limits(order_id)` — Đọc `olist_order_items_dataset.csv`, trả danh sách hạn chót bàn giao của Seller (`shipping_limit_date`) cho từng item.
  - `compare_delivery_timestamps(order_id, timeline, items)` — Thuật toán đối soát mốc thời gian ISO, xác định `is_late`, phân định `late_stage` (`seller`, `logistics`, `not_late`, `undetermined`), liệt kê Seller vi phạm và tạo danh sách `evidence_ids`.
- `tests/test_delivery_agent.py` — Chứa unit tests kiểm thử bộ công cụ và thuật toán so sánh mốc thời gian.
- `docs/checkpoints/tv4-cp1.md` — Báo cáo Checkpoint 1 của TV4.

## Thuật toán Phân định Trách nhiệm Trễ Hạn (Delay Classification Logic)

```text
               +----------------------------------+
               | Co delivered_customer_at &       |
               | estimated_delivery_at hay khong? |
               +----------------------------------+
                             |           |
                        Khong|           |Co
                             v           v
               +------------------+  +----------------------------------+
               | late_stage =     |  | delivered_customer_at >          |
               | "undetermined"   |  | estimated_delivery_at hay khong? |
               +------------------+  +----------------------------------+
                                           |             |
                                      Khong|             |Co
                                           v             v
                                     +----------+  +-----------------------------------+
                                     | not_late |  | Ton tai item co                   |
                                     +----------+  | delivered_carrier_at >            |
                                                   | shipping_limit_date hay khong?    |
                                                   +-----------------------------------+
                                                                 |          |
                                                            Khong|          |Co
                                                                 v          v
                                                           +-----------+  +--------+
                                                           | logistics |  | seller |
                                                           +-----------+  +--------+
```

## Lệnh kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_delivery_agent.py -k TestDeliveryTools -v
```

Kết quả: **5/5 tests passed** (Xác nhận 100% logic so sánh thời gian chính xác trên cả fixture và CSV Olist).
