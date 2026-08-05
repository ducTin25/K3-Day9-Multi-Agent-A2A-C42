# TV4 — Checkpoint 2 Handoff Report (DeliveryAgent & Security Allowlist)

## Trạng thái

`READY` — Đã hoàn thành `DeliveryAgent` (`src/agents/delivery.py`) xử lý tin nhắn chuẩn A2A `HandoffEnvelope`, tích hợp cơ chế bảo mật danh mục công cụ cho phép (Tool Allowlist) và đăng ký handler rời `delivery_agent_handler` vào `src/agents/registry.py`.

Không chỉnh sửa `docs/team-plan.md` trực tiếp để tránh xung đột git merge.

## Artifacts sở hữu

- `src/agents/delivery.py`:
  - `DELIVERY_AGENT_CONFIG` — Định nghĩa `agent_id="delivery_agent"`, role description, prompt_version `delivery-v1`, tool allowlist (`get_delivery_timeline`, `get_shipping_limits`, `compare_delivery_timestamps`), input/output schema.
  - `DELIVERY_SYSTEM_PROMPT` — Quy định nhiệm vụ phân định mốc thời gian giao hàng, giới hạn quyền hạn không gọi công cụ thanh toán hay hoàn tiền.
  - `DeliveryAgent` class — Chứa `validate_tool_access(tool_name)` (ném `PermissionError` nếu gọi công cụ ngoài allowlist) và `process_task(envelope) -> dict` (đọc `claimed_order_id`, gọi bộ công cụ CP1, trả về `DeliveryFacts`).
  - `delivery_agent_handler(envelope, data_dir=None, repository=None)` — Handler tương thích chữ ký `AgentHandler` cho runtime không đồng bộ (`src/runtime.py`).
- `src/agents/registry.py` — Đăng ký `delivery_agent_handler` vào danh sách hybrid handlers.
- `tests/test_delivery_agent.py` — Chứa unit test kiểm tra cơ chế bảo mật allowlist và tính hợp lệ của contract output.
- `docs/checkpoints/tv4-cp2.md` — Báo cáo Checkpoint 2 của TV4.

## Tự kiểm tra & Bảo mật (Tool Allowlist Verification)

1. **Tool Allowlist Security Enforcement**:
   - Gọi công cụ trong allowlist (`get_delivery_timeline`, `get_shipping_limits`, `compare_delivery_timestamps`) $\rightarrow$ PASSED.
   - Gọi công cụ thanh toán / hoàn tiền ngoài allowlist (`get_payments`, `execute_refund`) $\rightarrow$ Ném `PermissionError` chính xác.
2. **Contract Compliance**:
   - Trả về payload khớp 100% với schema `DeliveryFacts` (`src/contracts.py`).
   - `order_id` khớp định dạng 32 ký tự hex (`^[0-9a-f]{32}$`).
   - `late_stage` thuộc các giá trị chuẩn: `"seller"`, `"logistics"`, `"not_late"`, `"undetermined"`.
   - `evidence_ids` không vượt quá 10 phần tử.

## Lệnh kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_delivery_agent.py -k TestDeliveryAgent -v
```

Kết quả: **6/6 tests passed** (Bao gồm kiểm tra bảo mật allowlist và chuẩn giao tiếp A2A HandoffEnvelope).
