# TV5 — Checkpoint 1 handoff

## Trạng thái

`READY` — deterministic policy/verification tools và run reporting skeleton đã có test.

## Artifact sở hữu

- `src/tools/policy_tools.py`: áp dụng 6 rule `EC_POLICY_V1` theo đúng priority.
- `src/tools/verification_tools.py`: schema, policy mapping, financial, evidence và metadata/model gate.
- `src/tools/audit.py`: phát trace-compatible event qua callback; không tự ghi trace file.
- `src/schemas/output.schema.json`: output contract theo README.
- `src/schemas/metadata.schema.json`: metadata contract cho 6 logical agent.
- `scripts/summarize_run.py`: tạo `metrics.json` và `summary.md` cho từng run.
- `scripts/compare_runs.py`: so sánh baseline/candidate và báo regression.
- `tests/fixtures/policy/golden_cases.json`: đủ 6 policy branches.
- `config/model-selection.json`: ghi nhận model nhóm chọn và trạng thái compliance.

## Cách kiểm tra

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
```

Kết quả tại checkpoint: 13 tests pass.

## Contract tích hợp với TV1

- `evaluate_policy(bundle, trace_emit=..., trace_context=...) -> PolicyDecision`
- `verify_output(draft, evidence_lookup=..., trace_emit=..., trace_context=...) -> VerifyResult`
- Tool chỉ gọi `trace_emit(event)`; TV1 là owner duy nhất của filesystem trace writer.
- `summarize_run` đọc artifact trong `logging/runs/<run_id>/`, không đọc API key.
- `compare_runs` trả exit code `0` khi candidate không regression, `2` khi có regression.

## Model/API key

- Model ID cấu hình: `gpt-4o-mini`.
- API key chỉ đọc từ biến môi trường `OPENAI_API_KEY`; `.env` đã được ignore và không được ghi vào trace/metadata.
- Trang model chính thức xác nhận Structured Outputs và function calling nhưng không công bố parameter count: <https://developers.openai.com/api/docs/models/gpt-4o-mini>.
- Do bài yêu cầu model `<=10B`, `config/model-selection.json` hiện đặt `parameter_count=null`, `parameter_limit_status=unverified`, `promotion_allowed=false`.
- `validate_metadata` trả `MODEL_PARAMETER_COUNT_UNVERIFIED` cho cấu hình này. Không được tự điền một con số không có nguồn để vượt hard gate.

## Việc chuyển sang Checkpoint 2

1. TV1 nối trace callback vào append-only run writer và cung cấp `run_id/case_id/correlation_id`.
2. TV5 bọc hai deterministic tools thành hai invocation độc lập: PolicyAgent và VerifierAgent.
3. Dùng Structured Outputs cho response schema; không gửi API key trong request body/metadata.
4. Nhóm cần xin xác nhận của giảng viên về việc dùng closed model không công bố parameter count, hoặc đổi sang model có bằng chứng <=10B trước final run.
