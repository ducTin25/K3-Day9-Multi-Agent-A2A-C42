# Member Role Report — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                          |
| --------------- | --------------------------------- |
| Họ và tên       | Nguyễn Đức Tín                    |
| MSSV            | 2A202601185                       |
| Khóa/Lớp        | K3                                |
| Vai trò chính   | Tech Lead, Coordinator và Runtime |
| Ngày hoàn thành | 2026-08-05                        |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable              | File/hàm phụ trách                                                                                              | Input nhận vào                                            | Output bàn giao                                                           | Trạng thái |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------- | ---------- |
| Contract và cấu hình runtime    | `src/contracts.py`, `src/config.py`, `src/config/agents.yaml`                                                   | Yêu cầu đề bài, contract của TV2–TV5                      | Pydantic contract dùng chung, startup guard sáu agent, cấu hình `o4-mini` | Hoàn thành |
| A2A runtime và Coordinator      | `src/runtime.py`, `src/agents/coordinator.py`                                                                   | `CaseInput`, `HandoffEnvelope`, handler của các agent     | Fan-out ba domain, Policy → draft → Verifier, retry/repair có giới hạn    | Hoàn thành |
| Registry và tích hợp thành viên | `src/agents/registry.py`, `src/agents/tv5_handlers.py`                                                          | Handler Order/Seller, Payment, Delivery, Policy, Verifier | Registry hybrid và live; Policy/Verifier có context OpenAI độc lập        | Hoàn thành |
| Batch runner CP4                | `src/batch.py`, `src/runner.py`                                                                                 | 50 input `EC_001..EC_050`                                 | Chạy concurrent, cô lập lỗi từng case, reconciliation và run summary      | Hoàn thành |
| Ghi và kiểm chứng artifact      | `src/output_writer.py`, `trace.jsonl`, `metadata.json`, `logging/run_summary.json`                              | Draft output và `VerifyResult`                            | 50 JSON được ghi atomically sau verify; trace/metadata của run mới nhất   | Hoàn thành |
| Kiểm thử tích hợp TV1           | `tests/test_runtime_integration.py`, `tests/test_batch.py`, `tests/test_coordinator.py`, `tests/test_models.py` | Contract và handler đã tích hợp                           | Test retry, repair, batch isolation, Structured Outputs và flow sáu agent | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                   | Thành viên/module được hỗ trợ                                    | Kết quả                                                                                                |
| --------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Chuẩn hóa contract tích hợp | TV2 Order/Seller, TV3 Payment, TV4 Delivery, TV5 Policy/Verifier | Hợp nhất khác biệt tên field và nối handler vào runtime mà không chuyển logic nghiệp vụ về Coordinator |
| Xử lý merge và conflict     | Repo chung của nhóm                                              | Hoàn tất các merge CP2/CP3, giữ nguyên thay đổi thuộc ownership của thành viên khác                    |
| Thiết lập môi trường        | Toàn nhóm                                                        | Tạo `requirement.txt`, `.env.example`, venv và kiểm tra model/API mà không commit secret               |
| Kiểm chứng đầu ra           | TV5/output pipeline                                              | Chạy schema validation, đối soát 50 case và xác nhận trace đủ hoạt động của sáu logical agent          |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện           | File/hàm/artifact liên quan                                           | Kết quả bàn giao                                                                                               | Cách xác minh                                                            |
| ------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Xây contract A2A dùng chung     | `src/contracts.py`                                                    | Envelope có sender/receiver/message type/attempt; output các agent được validate bằng Pydantic                 | `pytest tests/test_contracts.py -q`                                      |
| Điều phối sáu agent             | `CoordinatorAgent`                                                    | Fan-out ba domain song song, sau đó Policy, draft assembly và Verifier                                         | `pytest tests/test_coordinator.py tests/test_runtime_integration.py -q`  |
| Targeted repair tối đa một vòng | `CoordinatorAgent._repair_once`                                       | Chỉ gọi lại agent được chỉ định bởi `repair_target`; giữ nguyên correlation ID và dùng `attempt=1`             | Các test repair Payment/Policy trong `tests/test_runtime_integration.py` |
| Cô lập lỗi batch                | `execute_batch`                                                       | Một case lỗi không dừng 49 case còn lại; summary ghi terminal/verified/written/missing                         | `pytest tests/test_batch.py -q`                                          |
| Tích hợp OpenAI live            | `build_live_handlers`, `run_live_case`, `run_live_batch`              | Policy và Verifier dùng hai client/context `o4-mini` độc lập, không dùng offline doubles trong chế độ `--live` | Canary `EC_004` và live batch 50 case                                    |
| Chạy CP4 toàn bộ dữ liệu        | `output/`, `trace.jsonl`, `metadata.json`, `logging/run_summary.json` | 50 received = 50 terminal = 50 verified = 50 written; 0 failed                                                 | `run_id=run-a572fa36-1a6e-4b44-a343-7c80d2866ef6`                        |

Output cụ thể của phần việc là batch live gồm đúng 50 file `output/EC_001.json` đến `output/EC_050.json`. Tất cả file khớp `case_id`, qua `src/schemas/output.schema.json`; `metadata.json` và `logging/run_summary.json` cùng run ID. Bộ test cuối đạt **118 passed và 49 subtests passed**.

Các commit chính của tôi gồm: `4856d78` (TV1 CP2), `a515df5` (tích hợp domain agent và writer), `ba64574` (CP3 targeted repair), `4e35912` (CP4 batch diagnostic) và `f66d0e5` (CP4 live OpenAI).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Hệ thống cần xử lý 50 khiếu nại bằng sáu vai trò tách biệt nhưng vẫn bảo đảm contract nhất quán, không trộn state giữa case, không để một lỗi làm dừng toàn batch và chỉ ghi output sau khi Verifier xác nhận. Coordinator không được tự suy luận nghiệp vụ thay cho domain agent hoặc Policy Agent.

### Cách triển khai

Mỗi case được gắn `run_id`, `case_id` và `correlation_id`. Coordinator tạo ba `TASK_REQUEST` và gọi Order/Seller, Payment, Delivery song song. Ba kết quả được validate thành `OrderSellerFacts`, `PaymentFacts`, `DeliveryFacts`, rồi ghép thành `InvestigationBundle`.

Bundle được chuyển qua `POLICY_REQUEST`; kết quả `PolicyDecision` được dùng để dựng draft deterministically. Coordinator gửi bundle, decision và draft trong `VERIFY_REQUEST`. Chỉ khi `VerifyResult.valid=true`, `AtomicOutputWriter` mới validate JSON Schema, ghi file tạm và dùng atomic replace để tạo output chính thức.

Nếu Verifier trả lỗi repairable, Coordinator đọc `repair_target`, chỉ gọi lại domain đích hoặc Policy, dùng cùng correlation ID và `attempt=1`, sau đó dựng lại bundle và chạy Policy → draft → Verifier. Runtime cấm attempt lớn hơn 1, vì vậy không thể có vòng repair vô hạn.

Ở CP4, `execute_batch` dùng semaphore để giới hạn concurrency. Exception được bắt trong phạm vi từng case, ghi `case_failed` và đưa vào summary; các case khác vẫn tiếp tục. Cuối run, runner đối soát tập case dự kiến với tập terminal, verified và written, đồng thời kiểm tra file thiếu hoặc thừa.

### Input, output và contract

| Thành phần              | Mô tả                                                                                                                                                       |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input                   | 50 `CaseInput` từ `input/EC_001.json` đến `input/EC_050.json`                                                                                               |
| Handoff                 | `HandoffEnvelope` schema version 1.0, có sender, receiver, message type, attempt và evidence IDs                                                            |
| Output nội bộ           | `OrderSellerFacts`, `PaymentFacts`, `DeliveryFacts`, `InvestigationBundle`, `PolicyDecision`, `VerifyResult`                                                |
| Output cuối             | Một JSON đúng output schema cho mỗi case và `CaseRunResult` cho runtime                                                                                     |
| Module phụ thuộc        | Handler của TV2–TV5, policy/verification tools, trace sink và output writer                                                                                 |
| Module sử dụng output   | Batch reconciliation, run summary và bộ artifact nộp bài                                                                                                    |
| Điều kiện lỗi cần xử lý | Input thiếu/trùng, envelope sai contract, timeout/transient error, model output sai schema, verifier reject, output thiếu/thừa hoặc case không đạt terminal |

### Cách xác minh

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.runner --batch --live --write-output --concurrency 2
```

- **Kết quả mong đợi:** toàn bộ test pass; đúng 50 case terminal, verified và written; không có output thiếu/thừa; không có schema error.
- **Kết quả thực tế:** 118 test và 49 subtest pass; 50 received, 50 terminal, 50 verified, 50 written, 0 failed.
- **Artifact/log:** `trace.jsonl`, `metadata.json`, `logging/run_summary.json`, `output/EC_001.json..EC_050.json`; không chứa API key hoặc secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Verifier có thể phát hiện lỗi của một domain, nhưng chạy lại toàn bộ sáu agent vừa tốn thời gian/API vừa làm thay đổi các kết quả vốn đã đúng.
- **Các phương án đã cân nhắc:** (1) fail ngay case; (2) chạy lại toàn pipeline không giới hạn; (3) targeted repair đúng agent bị lỗi, tối đa một vòng.
- **Phương án đã chọn:** targeted repair theo `VerifyError.repair_target`, giữ cùng correlation ID, tăng `attempt` lên 1 và luôn chạy lại Policy → draft → Verifier sau khi sửa.
- **Lý do:** giữ được tính đúng đắn và khả năng audit, tránh vòng lặp vô hạn, giảm invocation không cần thiết và không cho Coordinator tự sửa dữ liệu nghiệp vụ.
- **Bằng chứng quyết định phù hợp:** test cho Payment repair xác nhận Order/Seller và Delivery chỉ chạy một lần; test Policy repair xác nhận cả ba domain agent không bị gọi lại. Toàn bộ sáu nhánh nghiệp vụ đại diện đều đạt `VERIFIED`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** OpenAI trả HTTP 400: `Invalid schema for response_format 'VerifyResult' ... schema must have a 'type' key`.
- **Bước tái hiện:** chạy `python -m src.runner --case EC_004 --live` sau khi thay Policy/Verifier offline doubles bằng OpenAI client.
- **Nguyên nhân gốc:** `VerifyError.expected` và `VerifyError.actual` khai báo `Any`, khiến Pydantic sinh một node `{}` không có `type`; Structured Outputs không chấp nhận node schema không định kiểu.
- **Cách xử lý:** đổi hai field model-facing sang union scalar `str | int | float | bool | None`; rich diagnostics vẫn nằm trong trace/tool result. Thêm test duyệt JSON Schema để phát hiện node `{}`.
- **Cách xác minh sau khi sửa:** canary `EC_004` đạt `VERIFIED`, `stub=false`; batch live 50 case đạt 50/50 và test suite đạt 118 passed.
- **Điều học được:** Pydantic validation cục bộ chưa đủ để chứng minh schema tương thích provider; cần kiểm tra JSON Schema được sinh ra và chạy canary API trước batch lớn.

## 7. Hiểu biết về luồng end-to-end

Template gốc của mục này nhắc Crossref/vector index, không thuộc bài Day 9. Luồng end-to-end đúng của bài multi-agent thương mại điện tử như sau:

1. Preflight đọc 50 input, chuẩn hóa thành `CaseInput`, kiểm tra đủ và duy nhất `EC_001..EC_050`, sau đó dùng `claimed_order_id` để truy xuất dữ liệu Olist đã preprocess.
2. Coordinator fan-out tới Order/Seller, Payment và Delivery. Mỗi agent chỉ đọc domain/tool được cấp và trả facts kèm evidence ID có thể đối chiếu.
3. Coordinator ghép facts thành `InvestigationBundle`. Policy Agent áp dụng `EC_POLICY_V1` theo thứ tự ưu tiên để xác định issue, root cause, responsible party, refund và action.
4. Draft output được dựng từ bundle và policy decision. Verifier độc lập recompute policy, tài chính, evidence và schema; nếu lỗi repairable thì Coordinator thực hiện đúng một targeted repair.
5. Output chỉ được ghi atomically khi verify pass. Batch summary kiểm tra đủ 50 terminal/verified/written; `trace.jsonl` lưu handoff và invocation của run mới nhất, còn `metadata.json` ghi framework/runtime/model.
6. Cùng một bộ 50 case và cùng policy được dùng cho diagnostic và live run để có thể so sánh kết quả, phát hiện regression và không thay đổi test set theo output mong muốn.
7. Run được xem là thành công khi 50 received = 50 terminal = 50 verified = 50 written, 0 failed, 50 file qua JSON Schema, filename khớp case ID và trace có hoạt động của đủ sáu logical agent cho mỗi case.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Đức Tín  
**Ngày xác nhận:** 2026-08-05
