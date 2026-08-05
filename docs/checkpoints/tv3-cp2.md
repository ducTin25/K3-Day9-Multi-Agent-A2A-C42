# TV3 — Checkpoint 2 handoff (PaymentAgent)

## Trạng thái

`READY` — PaymentAgent thật (prompt + tool allowlist + structured output) đã có, test pass bằng dữ liệu CSV thật. Theo cùng pattern `DeliveryAgent` (TV4) để nhất quán trong repo.

## Artifact sở hữu

- `src/agents/payment.py`:
  - `PAYMENT_AGENT_CONFIG` — agent_id, role, prompt_version `payment-v1`, tool allowlist (`get_order_payments`, `get_order_financial_reference`, `reconcile_payments`), input/output schema.
  - `PAYMENT_SYSTEM_PROMPT` — quy tắc: chỉ dùng 3 tool trong allowlist, không nhân installments, Decimal + tolerance 0.10 BRL, không tự quyết delivery/refund.
  - `PaymentAgent` — `validate_tool_access()` (chặn tool ngoài allowlist), `process_task(envelope) -> dict` (đọc `claimed_order_id` từ payload, gọi 3 tool từ CP1, trả `PaymentFacts.model_dump(mode="json")`).
  - `payment_agent_handler(envelope, data_dir=None, repository=None)` — hàm rời tương thích chữ ký `AgentHandler` của `AgentRuntime` (`src/runtime.py`), sẵn sàng để TV1 cắm thay `payment_stub` ở CP3.
- `tests/test_payment_agent.py` — 6 test.

## Tự kiểm tra (đúng yêu cầu CP2: "Payment IDs đúng sequential; output dùng Decimal-derived totals")

- **Tool allowlist**: gọi tool ngoài danh sách (`issue_refund`, `get_delivery_timeline`) → `PermissionError`.
- **Payment IDs đúng sequential**: order thật 2 payment row (`0016dfedd97fc2950e388d2971d718c7`) → `evidence_ids = ["payment:...:1", "payment:...:2"]`, `payments[i].payment_sequential` tăng dần đúng thứ tự 1..N (`test_process_task_split_payment_ids_are_sequential`).
- **Decimal-derived totals, không nhân installments**: `payment_total_brl` luôn bằng tổng `payment_value_brl` của từng row, không nhân `payment_installments` (`test_output_uses_decimal_derived_totals_not_multiplied_by_installments`).
- **Output đúng contract `PaymentFacts`**: mọi kết quả được validate qua `PaymentFacts.model_validate()` trước khi assert.
- **Order không có payment**: trả `payment_count=0`, `payment_total_brl=0.00`, `evidence_ids=[]`, `is_reconciled=true` (không suy diễn evidence không tồn tại — README mục 5).

```powershell
.venv\Scripts\python.exe -m pytest tests/test_payment_agent.py -v
```

Kết quả: 6/6 pass. Full suite `pytest -q`: **72 passed**, không còn failure nào (lỗi `test_preflight.py` từ CP1 đã được TV1 sửa qua merge gần nhất).

## Việc chuyển sang Checkpoint 3 (tích hợp)

- `payment_agent_handler` đã đúng chữ ký `Callable[[HandoffEnvelope], Awaitable[dict]]` — TV1 chỉ cần đăng ký vào `AgentRuntime.handlers["payment_agent"]` thay cho `payment_stub` trong `src/agents/stubs.py`, không cần sửa gì thêm ở `coordinator.py`.
- Nhắc lại lưu ý field-name từ CP0/CP1: `PaymentFacts.is_reconciled` (contract) khác tên `is_reconciled_within_0_10` mà `policy_tools.py` đọc từ `InvestigationBundle.payment` — ai ráp `InvestigationBundle` ở CP3 cần map lại tên field này, nếu không Policy sẽ luôn coi `reconciled=False`.
- Chưa xử lý case order có nhiều seller/nhiều item nhưng ít payment — vẫn đúng vì Payment domain không quan tâm seller, chỉ đối soát tổng tiền; đã test qua order thật 1-item/1-payment và 1-item/2-payment.
