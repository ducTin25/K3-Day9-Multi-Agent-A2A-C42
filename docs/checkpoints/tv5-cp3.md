# TV5 — Checkpoint 3 handoff

## Trạng thái

`TV5_READY_WITH_INTEGRATION_BLOCKERS` — phạm vi PolicyAgent/VerifierAgent của thành viên 5 đã verify đủ 6 nhánh chính và 2 kịch bản targeted repair. Exit gate end-to-end của cả nhóm chưa thể đánh dấu hoàn tất vì Coordinator chưa nối vòng repair và atomic writer.

Không cập nhật checkbox trong `docs/team-plan.md` để tránh conflict khi các thành viên cùng push.

## Phần đã hoàn thành

- PolicyAgent và VerifierAgent tiếp tục chạy qua hai invocation/context độc lập của `AgentRuntime`.
- Verifier luôn recompute policy bằng deterministic tool trước khi chấp nhận kết quả model.
- Production `assemble_output` dựng draft deterministically từ bundle + decision; không gọi model, không ghi file và chỉ phát input/output hash vào trace.
- `assemble_tv5_draft` là interface bàn giao để TV1 nhận draft kèm `TraceEvent` chuẩn mà không cần dùng helper private.
- Khi Coordinator cung cấp `draft_output`, Verifier chạy thêm full output verification rồi hợp nhất lỗi về contract `VerifyResult`.
- Bổ sung kiểm tra chéo `item_total + freight_total == payment_total` cho `valid_split_payment` và `unsupported_late_claim` với tolerance BRL 0.10.
- Sai financial total sinh `FINANCIAL_TOTAL_MISMATCH` và route đúng tới `payment_agent`.
- Trace của repair giữ nguyên `run_id`, `case_id`, `correlation_id`, tăng `attempt=1`; test xác nhận không invoke lại agent miền không liên quan.

## Coverage Checkpoint 3

Sáu nhánh Policy → Verifier đều pass:

1. `canceled_order_paid`
2. `unavailable_order_paid`
3. `late_delivery_seller`
4. `late_delivery_logistics`
5. `valid_split_payment`
6. `unsupported_late_claim`

Hai kịch bản repair đều được inject lỗi và verify lại:

1. Sai policy: Verifier reject và đặt `repair_target=policy_agent`; sau khi PolicyAgent sửa, chỉ PolicyAgent và VerifierAgent chạy lại.
2. Sai payment total: Verifier reject với `FINANCIAL_TOTAL_MISMATCH`, đặt `repair_target=payment_agent`; sau khi draft được sửa, Verifier chạy lại và không gọi OrderSellerAgent/DeliveryAgent.

Các test này dùng fake structured model, không gọi API thật và không đọc/log `OPENAI_API_KEY`. Fake model chỉ echo authoritative deterministic tool result, vì vậy vẫn đi qua ranh giới invocation, trace và Pydantic contracts thật.

## Artifact thay đổi

- `src/agents/verifier.py`: full verification tùy chọn khi payload có `draft_output`, hợp nhất policy/output errors và giữ deterministic result là nguồn sự thật.
- `src/tools/output_tools.py`: production draft assembler, kiểm tra cross-order facts, entity/evidence limits, Decimal conversion và trace metadata.
- `src/agents/tv5_handlers.py`: interface `assemble_tv5_draft` dành cho Coordinator integration.
- `src/tools/verification_tools.py`: kiểm tra reconciliation tài chính và targeted repair về `payment_agent`.
- `tests/test_output_tools.py`, `tests/test_tv5_checkpoint3.py`: 6 representative branches, assembler contract/trace, policy repair, payment repair và trace assertions.

## Blocker tích hợp cần TV1 xử lý

### B1 — Coordinator chưa có targeted repair loop

`src/agents/coordinator.py` hiện kết thúc ngay sau lần gọi Verifier đầu tiên; chưa đọc `VerifyResult.errors[*].repair_target`, chưa gửi `REPAIR_REQUEST` và chưa giới hạn retry. Vì vậy hai repair scenario hiện được chứng minh ở integration harness của TV5, chưa chạy tự động qua graph của Coordinator.

TV1 cần:

1. Nếu `VerifyResult.valid=false` và lỗi repairable, group lỗi theo `repair_target`.
2. Gửi `REPAIR_REQUEST` với cùng run/case/correlation ID và `attempt=1` chỉ tới agent đích.
3. Nếu domain facts thay đổi, rebuild `InvestigationBundle`.
4. Luôn chạy lại PolicyAgent rồi VerifierAgent sau repair; không chạy lại domain agent không liên quan.
5. Chỉ cho phép một vòng repair, sau đó fail rõ ràng để tránh loop vô hạn.

### B2 — Coordinator chưa gọi interface draft và truyền kết quả cho Verifier

TV5 đã cung cấp production interface `assemble_tv5_draft(bundle, decision, policy_envelope, trace)`. Payload `VERIFY_REQUEST` của Coordinator hiện vẫn chỉ chứa `case`, `bundle`, `decision`, `stub`; TV1 cần gọi interface này và truyền kết quả dưới key `draft_output`. Nếu chưa nối, Verifier chỉ kiểm policy, chưa bắt lỗi financial/evidence/schema của output cuối.

### B3 — Chưa có atomic writer trong flow hiện tại

Graph chưa thể hiện bước chỉ ghi `output/EC_xxx.json` sau khi Verifier pass, ghi atomically rồi đọc/validate lại. Vì vậy exit gate “representative cases verified and written” của CP3 toàn nhóm vẫn đang block.

### B4 — Full suite có một lỗi preflight không liên quan TV5

`tests/test_preflight.py` yêu cầu `EC_050.source_file == "download"`, trong khi `run_preflight` đọc file hiện có `input/EC_050.json` và trả tên nguồn `"EC_050.json"`. Các file preflight/input này không nằm trong diff của TV5; owner preprocessing cần thống nhất lại fixture hoặc expectation. TV5 không tự sửa để tránh thay đổi phần sở hữu của thành viên khác.

## Điểm nối cho TV1

```python
from src.agents.tv5_handlers import assemble_tv5_draft, build_tv5_handlers

handlers.update(build_tv5_handlers(config, trace))
draft = assemble_tv5_draft(bundle, decision, policy_envelope, trace)

# VERIFY_REQUEST payload
{
    "bundle": bundle.model_dump(mode="json"),
    "decision": decision.model_dump(mode="json"),
    "draft_output": draft,
}
```

Model vẫn lấy từ cấu hình chung, không hard-code trong agent. Metadata hiện khai báo `o4-mini` và upper bound 10B theo xác nhận của nhóm; API key chỉ được đọc từ biến môi trường `OPENAI_API_KEY`.

## Lệnh kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_tv5_checkpoint3.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

Kết quả tại thời điểm bàn giao:

- Riêng CP3 TV5 và production assembler: `17 passed` (gồm 6 assembler subtests).
- Full suite: `52 passed`, `43 subtests passed`, `1 failed` tại blocker B4.
- `compileall`: pass.
- `git diff --check`: pass.
- `validate_metadata(metadata.json)`: pass, không có lỗi.
