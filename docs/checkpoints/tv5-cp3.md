# TV5 — Checkpoint 3 handoff

## Trạng thái

`READY` — sau khi đồng bộ code mới của TV1, toàn bộ phạm vi CP3 của TV5 đã chạy qua flow tích hợp: production draft assembly, full verification, targeted repair và atomic writer. Không còn blocker CP3.

Không cập nhật checkbox trong `docs/team-plan.md` để tránh conflict khi các thành viên cùng push.

## Phạm vi TV5 đã hoàn thành

- PolicyAgent và VerifierAgent là hai invocation/context độc lập qua `AgentRuntime`.
- PolicyAgent dùng deterministic `evaluate_ec_policy_v1`; model structured output không được phép khác authoritative tool result.
- `assemble_output` dựng draft deterministically từ `InvestigationBundle + PolicyDecision`, không gọi model và không ghi file.
- `assemble_tv5_draft` chuyển audit của assembler thành `TraceEvent` sanitized, chỉ chứa hash/summary.
- Verifier recompute policy và kiểm tra full `draft_output` trước khi trả `VerifyResult`.
- Financial mismatch route về `payment_agent`; policy mismatch route về `policy_agent`.
- Repair giữ cùng run/case/correlation ID, tăng `attempt=1`; domain agent không liên quan không chạy lại.

## Xác nhận tích hợp với TV1

Code sau pull đã giải quyết các blocker cũ:

1. Coordinator gọi `assemble_tv5_draft` và truyền `draft_output` vào `VERIFY_REQUEST`.
2. Coordinator đọc `repair_target`, chạy targeted repair tối đa một vòng rồi chạy lại Policy → Verifier.
3. Output chỉ được atomic-write sau khi Verifier trả `valid=true` và schema được kiểm lại.
4. Preflight EC_050 và full test suite hiện pass.

## Coverage sáu primary issue

Sáu representative case trong integration test:

| Case | Primary issue |
| --- | --- |
| `EC_003` | `canceled_order_paid` |
| `EC_005` | `unavailable_order_paid` |
| `EC_001` | `late_delivery_seller` |
| `EC_009` | `late_delivery_logistics` |
| `EC_004` | `valid_split_payment` |
| `EC_002` | `unsupported_late_claim` |

Tất cả được verify và atomic-write trong thư mục test tạm. Hai repair scenario `payment_agent` và `policy_agent` đều pass isolation assertions.

Artifact `output/` hiện có đúng 50 file `EC_001.json` đến `EC_050.json`, `case_id` bên trong khớp filename và bao phủ đủ sáu issue:

- `canceled_order_paid`: 8
- `unavailable_order_paid`: 8
- `late_delivery_seller`: 8
- `late_delivery_logistics`: 8
- `valid_split_payment`: 9
- `unsupported_late_claim`: 9

## Artifact TV5

- `src/agents/policy.py`
- `src/agents/verifier.py`
- `src/agents/tv5_handlers.py`
- `src/tools/policy_tools.py`
- `src/tools/output_tools.py`
- `src/tools/verification_tools.py`
- `src/schemas/output.schema.json`
- `tests/test_tv5_agents.py`
- `tests/test_output_tools.py`
- `tests/test_tv5_checkpoint3.py`

## Kiểm tra sau pull

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_tv5_checkpoint3.py tests/test_output_tools.py tests/test_tv5_agents.py tests/test_runtime_integration.py tests/test_output_writer.py
.\.venv\Scripts\python.exe -m pytest -q
```

Kết quả:

- CP3 TV5 + integration/writer: `31 passed`.
- Full suite: `118 passed`, `49 subtests passed`.
- Không gọi OpenAI API trong các test trên; không đọc hoặc log `OPENAI_API_KEY`.

## Bàn giao cho checkpoint tiếp theo

CP3 của TV5 đã `READY`. Công việc tiếp theo là CP4: chạy validator trên 50 output, bật evidence existence lookup, tạo summary và so sánh baseline/candidate run.
