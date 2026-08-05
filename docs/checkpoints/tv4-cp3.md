# TV4 — Checkpoint 3 Handoff Report

## Trạng thái
`TV4_READY` — Phạm vi của Thành viên 4 (DeliveryAgent & Handoff Analysis) đã hoàn thành và verified 100% cho toàn bộ 3 nhánh giao hàng chính cũng như tích hợp end-to-end với `PolicyAgent` và `VerifierAgent`.

Không chỉnh sửa `docs/team-plan.md` trực tiếp để tránh xung đột git merge khi các thành viên cùng làm việc.

## Phần đã hoàn thành (Checkpoint 3)

1. **Delivery Agent Core (`src/agents/delivery.py`)**:
   - `DeliveryAgent` nhận `TASK_REQUEST` envelope từ `CoordinatorAgent`, thực thi các công cụ allowlist (`get_delivery_timeline`, `get_shipping_limits`, `compare_delivery_timestamps`) và trả về `DeliveryFacts` chuẩn xác.
   - Giới hạn quyền truy cập công cụ (Tool Allowlist): Từ chối và ném `PermissionError` nếu gọi các công cụ tài chính/thanh toán ngoài danh mục.

2. **Delivery Tools (`src/tools/delivery_tools.py`)**:
   - Sử dụng thư viện chuẩn `csv` đọc dữ liệu Olist không phụ thuộc thư viện ngoài.
   - So sánh mốc thời gian ISO (`delivered_customer_at`, `estimated_delivery_at`, `delivered_carrier_at`, `shipping_limit_date`) chuẩn xác.

3. **Phân định 3 Nhánh Giao hàng Chính (Delivery Representative Branches)**:
   - **Nhánh 1: Giao đúng hạn (`not_late`)** $\rightarrow$ `is_late = False`, `late_stage = "not_late"`. Kết hợp với Policy ra quyết định `unsupported_late_claim` (`DELIVERY_WITHIN_ESTIMATE`).
   - **Nhánh 2: Seller bàn giao trễ (`seller`)** $\rightarrow$ `is_late = True`, `late_stage = "seller"`, chứa danh sách `violating_seller_ids`. Kết hợp với Policy ra quyết định `late_delivery_seller` (`SELLER_HANDOFF_AFTER_LIMIT`) quy trách nhiệm cho Seller.
   - **Nhánh 3: Logistics giao trễ (`logistics`)** $\rightarrow$ `is_late = True`, `late_stage = "logistics"`. Kết hợp với Policy ra quyết định `late_delivery_logistics` (`CARRIER_DELIVERED_AFTER_ESTIMATE`) quy trách nhiệm cho Logistics Provider.
   - **Trường hợp thiếu Timestamp (`undetermined`)** $\rightarrow$ `late_stage = "undetermined"`, phát tín hiệu cảnh báo trong `warnings`.

4. **Kiểm thử Tích hợp (`tests/test_delivery_checkpoint3.py`)**:
   - Kiểm thử 3 nhánh giao hàng đại diện kết hợp trực tiếp với `PolicyAgent`.
   - Kiểm thử tuân thủ chuẩn tin nhắn A2A `HandoffEnvelope`.

## Artifacts đã bàn giao

- `src/agents/delivery.py`
- `src/tools/delivery_tools.py`
- `tests/fixtures/delivery/on_time.json`
- `tests/fixtures/delivery/seller_late.json`
- `tests/fixtures/delivery/logistics_late.json`
- `tests/fixtures/delivery/missing_timestamp.json`
- `tests/test_delivery_agent.py`
- `docs/checkpoints/tv4-cp3.md`

## Lệnh kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_delivery_agent.py
.\.venv\Scripts\python.exe -m pytest
```

Kết quả: **77 passed** (toàn bộ 77 unit & integration tests trong dự án đều PASS).
