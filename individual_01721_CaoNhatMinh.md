# Báo cáo vai trò thành viên — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Cao Nhật Minh |
| MSSV | 2A202601721 |
| Khóa/Lớp | K3 |
| Vai trò chính | Thành viên 5 — PolicyAgent, VerifierAgent và quality gate |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Bộ luật quyết định `EC_POLICY_V1` | `src/tools/policy_tools.py`, `evaluate_policy` | `InvestigationBundle` | `PolicyDecision` theo đúng thứ tự ưu tiên sáu nhánh | Hoàn thành |
| PolicyAgent | `src/agents/policy.py`, `src/prompts/policy_v1.txt` | `POLICY_REQUEST` qua `HandoffEnvelope` | Structured `PolicyDecision` | Hoàn thành |
| VerifierAgent và quality gate | `src/agents/verifier.py`, `src/tools/verification_tools.py`, `src/prompts/verifier_v1.txt` | Bundle, policy decision và draft output | `VerifyResult` cùng lỗi và `repair_target` | Hoàn thành |
| Production draft assembler | `src/tools/output_tools.py`, `assemble_output`; `src/agents/tv5_handlers.py`, `assemble_tv5_draft` | Bundle đã đóng băng và policy decision | Draft đúng output schema, kèm trace hash | Hoàn thành |
| Schema và metadata gate | `src/schemas/output.schema.json`, `src/schemas/metadata.schema.json` | Output/metadata dạng JSON | Danh sách lỗi schema, model và contract | Hoàn thành |
| Run reporting skeleton | `scripts/summarize_run.py`, `scripts/compare_runs.py` | Artifact của baseline/candidate run | Metrics, summary và regression report | Hoàn thành phần công cụ |
| Kiểm thử TV5 | `tests/test_policy_tools.py`, `tests/test_verification_tools.py`, `tests/test_tv5_agents.py`, `tests/test_output_tools.py`, `tests/test_tv5_checkpoint3.py` | Golden fixtures và integration fakes | Coverage sáu policy branch và hai repair scenario | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Công bố interface tích hợp `assemble_tv5_draft` | TV1 — Coordinator/runtime | TV1 nối draft vào `VERIFY_REQUEST`, targeted repair và atomic writer mà không đưa domain logic vào Coordinator |
| Quy định taxonomy `repair_target` | TV1 và TV3 | Sai policy route tới `policy_agent`; sai tổng thanh toán route tới `payment_agent` |
| Review contract tài chính | TV3 — Payment/finance | Tolerance đối soát `0.10 BRL` và refund source được kiểm tra độc lập tại Verifier |
| Kiểm tra sau tích hợp | Toàn nhóm | Sáu representative case verify/write thành công; full suite đạt 118 test pass |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Mã hóa sáu rule theo đúng priority | `evaluate_policy`, golden fixture policy | Mỗi bundle chỉ sinh một issue/cause/party/refund/action xác định | `pytest -q tests/test_policy_tools.py` |
| Tách Policy và Verifier thành hai agent độc lập | `PolicyAgent`, `VerifierAgent`, `build_tv5_handlers` | Hai model client, system prompt và invocation trace riêng | `pytest -q tests/test_tv5_agents.py` |
| Dựng output cuối | `assemble_output`, `assemble_tv5_draft` | Entity, evidence, financial resolution và root cause ổn định, không tự ghi file | `pytest -q tests/test_output_tools.py` |
| Reject và route lỗi | `verify_policy`, `verify_output` | Lỗi financial về PaymentAgent; lỗi policy về PolicyAgent | `pytest -q tests/test_tv5_checkpoint3.py` |
| Xác nhận CP3 end-to-end | `tests/test_runtime_integration.py`, `docs/checkpoints/tv5-cp3.md` | Sáu issue đều `VERIFIED`, repair isolation pass và output được atomic-write | `pytest -q tests/test_runtime_integration.py` |
| Kiểm tra regression toàn repo | Toàn bộ test suite | `118 passed, 49 subtests passed` | `python -m pytest -q` |

Một artifact cụ thể do phần việc của tôi tạo ra là draft output sau `assemble_output`. Draft gồm `assessment`, `affected_entities`, `root_cause_analysis`, `evidence_ids`, `financial_resolution` và `resolution_actions`. Coordinator chỉ được ghi draft này thành `output/EC_xxx.json` sau khi Verifier trả `valid=true`.

Các commit chính có thể đối chiếu trong Git history gồm `c192aa2` (policy/verifier và run reporting), `c5c12fa` (CP2) và `48f5f7f` (CP3 assembler, verifier, tests).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline nhận facts từ ba domain agent nhưng không thể để model tự quyết định tùy ý hoặc tự ghi output. Hệ thống cần một PolicyAgent áp dụng chính xác `EC_POLICY_V1`, một VerifierAgent độc lập có quyền reject, và một draft assembler xác định để cùng input luôn tạo cùng output. Khi có lỗi, Verifier phải chỉ rõ agent cần sửa để Coordinator không chạy lại toàn bộ pipeline.

### Cách triển khai

Policy evaluator áp dụng rule theo thứ tự ưu tiên:

1. Order bị hủy nhưng đã thanh toán.
2. Order unavailable nhưng đã thanh toán.
3. Giao trễ do seller handoff sau hạn.
4. Giao trễ thuộc logistics.
5. Split payment hợp lệ và đã đối soát.
6. Khiếu nại giao trễ không được dữ liệu hỗ trợ.

PolicyAgent trước hết gọi deterministic tool để lấy kết quả authoritative. Model nhận structured context và phải trả đúng `PolicyDecision`; nếu khác tool result, invocation thất bại thay vì âm thầm chấp nhận hallucination.

Draft assembler lấy facts và decision đã validate để tạo output. Nó kiểm tra order ID của OrderSeller, Payment và Delivery đều khớp order người dùng khiếu nại; chuẩn hóa tiền về hai chữ số; giới hạn và sắp xếp ID ổn định; ưu tiên giữ policy evidence trong giới hạn 10 evidence. Tool không ghi filesystem và trace chỉ chứa hash/summary.

Verifier có context và model client riêng. Nó recompute policy, kiểm schema/danh sách/enum, financial total, refund source, evidence format và policy mapping. Kết quả deterministic là nguồn sự thật; model không được override. Lỗi được trả về dưới dạng `VerifyResult.errors`, có `repair_target` để Coordinator repair đúng agent tối đa một vòng.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input PolicyAgent | `HandoffEnvelope(message_type="POLICY_REQUEST")`, payload là `InvestigationBundle` |
| Output PolicyAgent | `PolicyDecision`: issue, status, confidence, causes, parties, refund, actions và policy evidence |
| Input assembler | `InvestigationBundle + PolicyDecision` |
| Output assembler | Dictionary tuân thủ `src/schemas/output.schema.json` |
| Input VerifierAgent | `VERIFY_REQUEST` chứa bundle, decision và `draft_output` |
| Output VerifierAgent | `VerifyResult(valid, repairable, errors[])` |
| Module phụ thuộc | Contracts của TV1 và facts từ TV2/TV3/TV4 |
| Module sử dụng output | TV1 Coordinator, targeted repair và `AtomicOutputWriter` |
| Điều kiện lỗi | Sai receiver/message type, facts chéo order, model khác tool result, sai policy/refund/tổng tiền/schema/evidence format |

### Cách xác minh

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_tv5_checkpoint3.py tests/test_output_tools.py tests/test_tv5_agents.py tests/test_runtime_integration.py tests/test_output_writer.py
.\.venv\Scripts\python.exe -m pytest -q
```

- **Kết quả mong đợi:** sáu issue branch pass; lỗi payment/policy route đúng; repair không gọi lại domain agent không liên quan; output chỉ được ghi sau verify.
- **Kết quả thực tế:** 31 test CP3/integration pass; toàn repo `118 passed, 49 subtests passed`.
- **Artifact/log:** `docs/checkpoints/tv5-cp3.md`, `trace.jsonl` và 50 file trong `output/`; không chứa API key.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Nếu dùng trực tiếp câu trả lời của LLM làm policy decision, kết quả có thể thay đổi giữa các lần chạy hoặc vi phạm priority/refund rule.
- **Các phương án đã cân nhắc:** (1) để model tự suy luận và chỉ validate schema; (2) dùng deterministic policy tool rồi yêu cầu model structured output phải khớp tuyệt đối; (3) bỏ model hoàn toàn và chỉ dùng hàm Python.
- **Phương án đã chọn:** dùng deterministic tool làm nguồn sự thật, nhưng vẫn giữ PolicyAgent và VerifierAgent là hai invocation độc lập có structured model output.
- **Lý do:** phương án này vừa đáp ứng kiến trúc multi-agent/model invocation, vừa đảm bảo correctness và reproducibility. Model không thể thay đổi refund hoặc priority; Verifier vẫn có context độc lập để kiểm chéo.
- **Bằng chứng:** sáu golden branch pass; test cố tình cho model trả khác authoritative result làm invocation fail; full integration vẫn đạt `VERIFIED` cho sáu case đại diện.

## 6. Một blocker đã xử lý

- **Triệu chứng:** CP3 ban đầu chỉ chứng minh Policy/Verifier bằng harness; Coordinator chưa truyền `draft_output`, chưa có targeted repair và chưa atomic-write output.
- **Bước tái hiện:** đọc trace/integration flow cũ hoặc chạy test Coordinator cho thấy flow kết thúc sau lần verify đầu, payload chỉ có bundle và decision.
- **Nguyên nhân gốc:** ranh giới bàn giao giữa module TV5 và orchestration TV1 chưa có production interface cho draft và chưa thống nhất `repair_target`.
- **Cách xử lý trong phạm vi của tôi:** xây `assemble_output`, công bố `assemble_tv5_draft`, bổ sung full-output verification và error routing; viết test sáu branch cùng hai repair scenario. TV1 sau đó nối interface này vào Coordinator, repair loop và writer.
- **Cách xác minh sau khi sửa:** `tests/test_runtime_integration.py` xác nhận đủ sáu agent boundary, hai targeted repair và atomic write; 31 test liên quan CP3 pass.
- **Điều học được:** contract bàn giao và ownership phải được chốt trước; một module có thể hoàn chỉnh riêng nhưng exit gate end-to-end chỉ đạt khi có integration test qua ranh giới thật.

## 7. Hiểu biết về luồng end-to-end

1. Runner chạy preflight để chuẩn hóa 50 case `EC_001`–`EC_050`, kiểm thiếu/trùng/sai order ID và nạp cấu hình sáu model. API key chỉ lấy từ biến môi trường, không nằm trong payload hoặc trace.
2. Coordinator tạo `run_id` và `correlation_id`, sau đó fan-out ba `TASK_REQUEST` song song tới OrderSellerAgent, PaymentAgent và DeliveryAgent. Ba agent chỉ được dùng tool trong allowlist và trả facts theo contract.
3. Coordinator validate rồi fan-in các facts thành `InvestigationBundle`. PolicyAgent nhận bundle qua `POLICY_REQUEST`, áp dụng `EC_POLICY_V1` theo priority và trả `PolicyDecision`.
4. Draft assembler tạo output xác định từ bundle và decision. Coordinator gửi bundle, decision và draft tới VerifierAgent bằng `VERIFY_REQUEST`.
5. Verifier recompute policy và kiểm schema, mapping, money/refund và evidence. Nếu hợp lệ, Coordinator cho atomic writer ghi `output/EC_xxx.json`. Nếu lỗi repairable, Coordinator chỉ gọi lại agent nằm trong `repair_target`, rebuild bundle khi cần, rồi chạy lại Policy và Verifier với `attempt=1`.
6. Batch runner cô lập lỗi theo case để một case thất bại không làm mất terminal state của các case khác. Trace lưu invocation, attempt, duration, hash và trạng thái để phân tích lần chạy sau.
7. `summarize_run.py` tạo metrics/summary; `compare_runs.py` so candidate với baseline bằng cùng tập 50 case. Cùng test set là điều kiện cần để chênh lệch phản ánh thay đổi code/model thay vì thay đổi dữ liệu đầu vào.
8. Một repair được xem là thành công khi candidate không tạo regression chưa giải thích, case được Verifier chấp nhận, output được ghi đúng schema, agent không liên quan không chạy lại và trace thể hiện rõ correlation tree.

Tại lần kiểm tra cuối, thư mục output có đủ 50 file, `case_id` khớp filename và bao phủ cả sáu primary issue: canceled 8, unavailable 8, seller-late 8, logistics-late 8, valid-split 9 và unsupported-late 9.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phạm vi công việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Cao Nhật Minh  
**Ngày xác nhận:** 2026-08-05
