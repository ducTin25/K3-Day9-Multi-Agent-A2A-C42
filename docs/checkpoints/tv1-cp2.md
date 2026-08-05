# TV1 — Checkpoint 2 integration handoff

## Trạng thái

`PARTIAL READY` — runtime, retry, hybrid registry và structured handoff đã chạy được. TV4 Delivery và TV5 Policy/Verifier dùng implementation thật; TV2 OrderSeller và TV3 Payment vẫn dùng contract-safe stub trong chế độ hybrid cho đến khi hai CP2 agent được bàn giao.

## Artifact TV1

- `src/runtime.py`: timeout, retry tối đa một lần cho lỗi tạm thời, không retry contract error, trace riêng từng attempt.
- `src/agents/registry.py`: registry hybrid với TV4/TV5 thật và TV2/TV3 stub.
- `src/runner.py`: CLI `--hybrid`, metadata ghi `mode=hybrid_cp2`.
- `tests/test_runtime_integration.py`: retry isolation, non-retryable contract errors và flow đủ sáu logical agent.

## Tự kiểm tra

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m src.runner --case EC_001 --hybrid
```

Kết quả tại thời điểm bàn giao: `69 passed, 43 subtests passed`; hybrid case `EC_001` đạt `VERIFIED` mà không gọi OpenAI API.

## Việc còn lại để CP2 READY

1. Thay `order_seller_agent` stub bằng handler CP2 của TV2.
2. Thay `payment_agent` stub bằng handler CP2 của TV3.
3. Chạy integration test với đủ ba domain agent thật.
4. Bổ sung targeted repair tối đa một vòng sau khi TV5 thống nhất `repair_target` cho output draft thực.

