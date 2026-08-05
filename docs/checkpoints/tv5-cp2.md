# TV5 — Checkpoint 2 handoff

## Trạng thái

`READY` — PolicyAgent và VerifierAgent đã là hai invocation/context độc lập, có prompt, tool allowlist, structured output và trace riêng.

## Artifact

- `src/agents/policy.py`: handler `POLICY_REQUEST`, gọi `evaluate_ec_policy_v1`, sau đó model structured output `PolicyDecision`.
- `src/agents/verifier.py`: handler `VERIFY_REQUEST`, tự recompute bằng `verify_policy_decision`, sau đó model structured output `VerifyResult`.
- `src/agents/tv5_handlers.py`: factory tạo hai model client riêng và trả hai handler cho TV1 runtime.
- `src/agents/_support.py`: prompt loader, allowlist guard và adapter tool event → `TraceEvent` của TV1.
- `src/prompts/policy_v1.txt`, `src/prompts/verifier_v1.txt`: hai system prompt không dùng chung context.
- `tests/test_tv5_agents.py`: invocation independence, rejection/repair route, model disagreement trace và handler factory tests.

## Luồng tích hợp

```python
config = load_runtime_config()
trace = TraceSink(run_trace_path)
handlers = domain_handlers()
handlers.update(build_tv5_handlers(config, trace))
runtime = AgentRuntime(trace, handlers)
coordinator = CoordinatorAgent(runtime)
```

Coordinator không gọi trực tiếp TV5 tools. Nó gửi `POLICY_REQUEST` và `VERIFY_REQUEST` qua `AgentRuntime`, do đó trace có `invocation_started`, tool event và `invocation_succeeded/failed` cho từng agent.

## Guardrail

- Chỉ nhận đúng receiver/message type.
- Validate payload bằng `InvestigationBundle`, `PolicyDecision`, `VerifyResult` remote contracts.
- Mỗi agent chỉ chạy tool có trong allowlist metadata.
- Deterministic tool là nguồn sự thật; model output khác tool result làm invocation fail, không tự sửa hoặc bỏ qua.
- Verifier không dùng PolicyAgent model client, system prompt hay message history.
- Tool không tự ghi file; adapter gửi `TraceEvent` qua `TraceSink` của TV1.
- Không đọc/log `OPENAI_API_KEY`; model factory hiện có chịu trách nhiệm đọc biến môi trường.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_tv5_agents.py
.\.venv\Scripts\python.exe -m pytest -q
```

Kết quả lúc bàn giao: 27 tests và 8 subtests pass; `metadata.json` pass metadata gate.

## Lưu ý model

Code không hard-code model trong agent. Nó dùng model từ `src/config/agents.yaml`; hiện config chung là `o4-mini` với upper bound do nhóm attested. Đây là quyết định config của nhóm, không phải logic TV5.
