# Logging, tracing và cải tiến qua từng lần chạy

## 1. Mục tiêu

Hệ thống phải trả lời được cho mỗi lần chạy:

- Agent nào xử lý case nào, dùng model/prompt/tool nào?
- Fact/evidence được handoff từ đâu tới đâu?
- Policy chọn nhánh nào và vì sao?
- Verifier reject lỗi gì, lỗi thuộc owner/module nào?
- Repair có cải thiện kết quả hay không?
- Run mới tốt hơn hay kém run trước ở correctness, completion, latency và stability?

README yêu cầu `trace.jsonl` chỉ chứa lượt chạy mới nhất. Vì vậy hệ thống tách hai lớp:

1. `logging/runs/<run_id>/`: lịch sử bất biến dùng để phân tích và cải tiến.
2. Root `trace.jsonl`: bản sanitized của run được promote để nộp; luôn bị thay thế, không append lịch sử.

## 2. Cấu trúc artifact theo run

```text
logging/
  runs/
    <run_id>/
      run.json
      trace.jsonl
      cases.jsonl
      errors.jsonl
      verifier_feedback.jsonl
      metrics.json
      summary.md
      config_snapshot.json
  comparisons/
    <baseline>__<candidate>.json
    <baseline>__<candidate>.md
trace.jsonl
metadata.json
```

| Artifact | Mục đích |
| --- | --- |
| `run.json` | Trạng thái run, start/end time, git SHA, dataset checksum, input checksum |
| `trace.jsonl` | Event-level trace của agent, tool và A2A handoff |
| `cases.jsonl` | Một record tổng hợp cho mỗi case |
| `errors.jsonl` | Lỗi đã chuẩn hóa theo code, owner, stage và repairability |
| `verifier_feedback.jsonl` | Mọi reject/warning của Verifier, kể cả lỗi đã repair thành công |
| `metrics.json` | Metric máy đọc được của run |
| `summary.md` | Báo cáo ngắn cho nhóm đọc và quyết định việc cải thiện |
| `config_snapshot.json` | Model <=10B, prompt/tool/schema versions và decoding settings của 6 agent |

Không lưu `.env`, API key, token, authorization header hoặc secret. Raw model response chỉ lưu khi thật sự cần debug và phải qua redaction; mặc định lưu structured response/hash/summary.

## 3. Run identity và khả năng tái hiện

`run_id` có dạng dễ đọc nhưng duy nhất, ví dụ `20260805T103015+0700_a1b2c3d`. Mọi artifact/event phải có:

- `run_id`;
- `case_id` nếu là event theo case;
- git commit SHA hoặc working-tree fingerprint;
- input manifest checksum;
- raw/processed dataset checksum;
- `EC_POLICY_V1` và schema version;
- model name, parameter count, provider/runtime;
- prompt version/hash và tool version/hash;
- random seed/temperature/top-p/max tokens;
- timestamp và duration.

Thiếu config/checksum làm run bị đánh dấu `non_reproducible=true` và không được promote làm bản nộp.

## 4. Event schema

Mỗi dòng trace là một JSON object theo schema thống nhất:

```json
{
  "schema_version": "1.0",
  "run_id": "20260805T103015+0700_a1b2c3d",
  "event_id": "<uuid>",
  "parent_event_id": "<uuid-or-null>",
  "case_id": "EC_001",
  "correlation_id": "EC_001:delivery:attempt-0",
  "sequence": 17,
  "timestamp": "<ISO-8601>",
  "event_type": "AGENT_RESPONSE",
  "stage": "domain_investigation",
  "agent_id": "delivery_agent",
  "model_name": "<model-name>",
  "parameter_count": 8000000000,
  "prompt_version": "delivery-v1",
  "attempt": 0,
  "sender": "delivery_agent",
  "receiver": "coordinator_agent",
  "message_type": "FACT_RESPONSE",
  "tool_calls": ["get_delivery_timeline", "get_shipping_limits"],
  "input_hash": "<sha256>",
  "output_hash": "<sha256>",
  "evidence_ids": ["order:<id>", "item:<id>:1"],
  "status": "success",
  "duration_ms": 324,
  "usage": {
    "input_tokens": 410,
    "output_tokens": 185
  },
  "error": null
}
```

`sequence` tăng đơn điệu trong một run. `parent_event_id` tạo cây quan hệ từ Coordinator request tới agent/tool/response. Ghi event theo kiểu append-only trong thư mục run; mỗi dòng flush ngay để vẫn điều tra được khi process crash.

## 5. Các event bắt buộc

| Event | Khi ghi |
| --- | --- |
| `RUN_STARTED` | Sau khi tạo run directory và config snapshot |
| `MODEL_GUARD_PASSED/FAILED` | Sau kiểm model/fallback <=10B |
| `PREPROCESS_STARTED/COMPLETED/FAILED` | Khi chạy/kiểm DP-01 |
| `CASE_RECEIVED` | Khi Coordinator nhận case hợp lệ |
| `HANDOFF_SENT/RECEIVED` | Mỗi A2A envelope sender/receiver |
| `AGENT_STARTED/RESPONSE/FAILED` | Mỗi invocation độc lập |
| `TOOL_STARTED/COMPLETED/FAILED` | Mỗi tool call, kèm duration và row count/hash |
| `BUNDLE_CREATED` | Sau fan-in ba domain facts |
| `POLICY_DECIDED/UNRESOLVED` | Policy result và matched rule |
| `VERIFY_PASSED/REJECTED` | Verifier result và error codes |
| `REPAIR_REQUESTED/COMPLETED/FAILED` | Vòng repair và target agent |
| `OUTPUT_WRITTEN` | Sau atomic write + re-parse thành công |
| `CASE_COMPLETED/FAILED` | Terminal state của case |
| `RUN_COMPLETED/FAILED` | Terminal state và summary metrics |

Một case thành công bình thường phải thể hiện invocation riêng của cả 6 logical agent. Trace thiếu agent/handoff bắt buộc là lỗi audit, dù output JSON đúng.

## 6. Error taxonomy và ownership

Error code phải ổn định để so sánh giữa run:

| Prefix | Owner chính | Ví dụ |
| --- | --- | --- |
| `INPUT_*`, `RUNTIME_*`, `MODEL_*`, `HANDOFF_*` | TV1 | duplicate case, timeout, model >10B, envelope sai |
| `PREPROCESS_*`, `ORDER_*`, `ITEM_*`, `SELLER_*` | TV2 | parse/join/orphan/entity mismatch |
| `PAYMENT_*`, `FINANCIAL_*` | TV3 | tổng payment/refund/tolerance sai |
| `DELIVERY_*`, `TIMESTAMP_*` | TV4 | late stage/timestamp comparator sai |
| `POLICY_*`, `SCHEMA_*`, `EVIDENCE_*`, `VERIFY_*` | TV5 | priority/mapping/schema/evidence sai |

Mỗi error record gồm `error_code`, `severity`, `owner`, `stage`, `case_id`, `agent_id`, `attempt`, `repairable`, `message`, `expected`, `actual`, `evidence_ids` và `reproduction_hint`.

## 7. Metrics của một run

### Correctness và completeness

- `cases_received`, `cases_verified`, `cases_written`, `cases_failed`;
- `schema_pass_rate`, `evidence_pass_rate`, `financial_pass_rate`, `policy_pass_rate`;
- số case theo từng `primary_issue`;
- số error theo code/owner/agent;
- `first_pass_verify_rate`;
- `repair_success_rate`;
- số output thay đổi so với baseline theo field/path.

### Multi-agent integrity

- invocation count theo agent;
- handoff count và missing handoff count;
- tool call count/out-of-allowlist attempts;
- model guard failures;
- số case có đủ 6 agent invocation;
- schema retry/timeout count.

### Hiệu năng và stability

- duration toàn run và p50/p95 theo case/agent/tool;
- input/output token usage theo agent nếu runtime cung cấp;
- retry rate, timeout rate;
- deterministic output rate khi chạy lại cùng config/checksum;
- peak memory/index build time nếu đo được.

Không tối ưu latency/token nếu làm giảm correctness hoặc auditability.

## 8. So sánh và cải tiến run

Sau mỗi run, thực hiện:

1. Chạy `scripts/summarize_run.py <run_id>` để tạo metrics/summary.
2. Chọn baseline gần nhất đã verified hoặc run đang được promote.
3. Chạy `scripts/compare_runs.py <baseline> <candidate>`.
4. Tạo diff theo case và JSON path, phân nhóm error theo owner.
5. Mỗi owner chọn lỗi có tần suất/impact cao nhất, sửa code/prompt/tool/schema đúng ownership.
6. Chạy unit/golden tests liên quan rồi chạy lại đúng tập 50 case với config snapshot mới.
7. Chỉ promote candidate nếu hard gates pass và không có regression không được giải thích.

Tiêu chí candidate tốt hơn baseline:

- `cases_verified` không giảm;
- schema/evidence/financial/policy pass rate không giảm;
- số case first-pass verified tăng hoặc giữ nguyên;
- không xuất hiện model >10B hoặc missing handoff;
- output diff phải giải thích được bằng commit/prompt/tool version;
- latency/token có thể tăng nếu correctness tăng, nhưng phải ghi trade-off trong summary.

## 9. Promote run để nộp

Chỉ TV1 promote sau khi TV2–TV5 ký audit:

```text
candidate run passes 50/50
    -> copy/sanitize logging/runs/<run_id>/trace.jsonl
    -> atomically replace root trace.jsonl
    -> generate root metadata.json from config_snapshot.json
    -> write promoted_run_id into metadata.json
    -> run final submission validator
```

Không xóa run history khi promote. Root `trace.jsonl` không append; nó chỉ phản ánh run được chọn. `logging/runs/` không được đưa vào output zip.

## 10. Phân công logging

| Thành viên | Trách nhiệm |
| --- | --- |
| TV1 | Trace writer, run directory, config snapshot, correlation tree, promote command |
| TV2 | DP-01 metrics, order/item/seller error context và data manifest |
| TV3 | Financial recompute metrics và payment error diagnostics |
| TV4 | Delivery/timestamp diagnostics và classification distribution |
| TV5 | Verifier feedback, run summary, compare-runs report và regression gate |

Mỗi checkpoint integration/full run phải kết thúc bằng một `summary.md` ngắn: kết quả, top errors, owner, thay đổi đề xuất và tiêu chí xác minh ở run kế tiếp.
