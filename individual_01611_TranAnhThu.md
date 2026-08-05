# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                        |
| --------------- | ------------------------------------------------ |
| Họ và tên       | Trần Anh Thư                                     |
| MSSV            | 2A202601611                                      |
| Khóa/Lớp        | K3                                                |
| Vai trò chính   | TV3 — Payment Agent & Financial Reconciliation    |
| Ngày hoàn thành | 2026-08-05                                        |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| CP0 — Payment fixtures | `tests/fixtures/payment/*.json` (7 fixture: single/split/zero/mismatch/boundary 0.09-0.10-0.11) | Contract `PaymentFacts` (`src/contracts.py`) | `tests/test_payment_fixtures.py`, bảng test biên (`docs/checkpoints/tv3-cp0.md`) | Hoàn thành |
| CP1 — Payment tools + finance helpers | `src/finance.py`, `src/tools/payment_tools.py` | CSV `olist_order_payments_dataset.csv`, `olist_order_items_dataset.csv` | `get_order_payments`, `get_order_financial_reference`, `reconcile_payments`; test `tests/test_finance.py`, `tests/test_payment.py` | Hoàn thành |
| CP2 — PaymentAgent | `src/agents/payment.py` (`PaymentAgent`, `payment_agent_handler`) | `HandoffEnvelope` (TASK_REQUEST từ Coordinator) | `PaymentFacts` payload đúng contract; test `tests/test_payment_agent.py` | Hoàn thành |
| CP3 — Financial audit (review chéo) | `tests/test_financial_audit.py` | `tests/fixtures/policy/golden_cases.json` (TV5), CSV thật | Đối chiếu order totals TV2↔TV3 (40 order thật) + recompute 6 rule refund độc lập với `evaluate_policy()` (TV5); `docs/checkpoints/tv3-cp3.md` | Hoàn thành |
| CP4 — Recompute 50 case thật | `tests/test_cp4_financial_recompute.py` | `output/EC_001..050.json` (run thật của TV1) | Xác nhận 0 mismatch PAYMENT_*/FINANCIAL_*; `docs/checkpoints/tv3-cp4.md` | Hoàn thành |
| CP5 — Financial audit summary | `scripts/audit_financials.py` | `output/EC_*.json` + `data/*.csv` | `docs/checkpoints/tv3-financial-audit-summary.md`, `logging/tv3_financial_audit.json` | Hoàn thành |

Tôi chỉ nhận ownership các file trong bảng trên (domain Payment/Finance). Các domain khác (OrderSeller — TV2, Delivery — TV4, Policy/Verifier — TV5, Coordinator/runtime — TV1) tôi chỉ đọc để tích hợp, không sửa trực tiếp.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả và bằng chứng |
| --- | --- | --- |
| Review chéo logic đối soát tài chính | TV5 (`src/tools/verification_tools.py`, `src/tools/output_tools.py`) | Xác nhận `PAYMENT_TOLERANCE=0.10` inclusive và rounding `ROUND_HALF_UP` khớp giữa `finance.py` (TV3) và `verification_tools.py`/`policy_tools.py` (TV5) — ghi trong `docs/checkpoints/tv3-cp3.md` |
| Phát hiện & báo cáo blocker tích hợp | TV1 (`src/agents/registry.py`) | Phát hiện `build_hybrid_handlers` chưa wire `payment_agent`/`order_seller_agent` thật (còn dùng stub) tại thời điểm CP3 — báo trong `docs/checkpoints/tv3-cp3.md`; xác nhận TV1 đã wire xong khi audit lại ở CP4 |
| Phát hiện rủi ro cấu trúc | TV2 (`src/data/olist_repository.py`) | `item_total_brl`/`freight_total_brl` được tính độc lập ở 2 nơi (TV2 và TV3, không dùng chung hàm) — không gây lỗi số liệu tại thời điểm audit (đối chiếu khớp 100% trên 40 rồi 50 order thật) nhưng ghi nhận là rủi ro maintainability cho cả nhóm |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây Decimal/rounding helper dùng chung cho tiền | `src/finance.py` (`to_money`, `sum_money`, `reconciliation_delta`, `is_within_tolerance`) | Chuẩn hoá parsing tiền: `Decimal`, quantize 2dp `ROUND_HALF_UP`, tolerance `0.10` inclusive | `pytest tests/test_finance.py -v` → 10 test pass |
| Xây Payment tools đọc CSV thật | `src/tools/payment_tools.py` | `PaymentFacts` payload từ order thật, không nhân `payment_installments` | `pytest tests/test_payment.py -v` → 10 test pass (gồm 2 order thật: 1-payment và 2-payment split) |
| Xây PaymentAgent (prompt + tool allowlist) | `src/agents/payment.py` | Handler tương thích `AgentRuntime`, sẵn sàng để TV1 wire vào Coordinator | `pytest tests/test_payment_agent.py -v` → 6 test pass |
| Audit tài chính độc lập trên 50 case thật | `tests/test_cp4_financial_recompute.py`, `scripts/audit_financials.py` | 0 mismatch item/freight/payment/refund trên toàn bộ 50 case đã chạy thật qua live OpenAI | `python scripts/audit_financials.py` → `cases_with_findings: 0`; report tại `docs/checkpoints/tv3-financial-audit-summary.md` |

Một output cụ thể: `docs/checkpoints/tv3-financial-audit-summary.md` — báo cáo audit tài chính cuối cùng, xác nhận cả 50/50 output thật đều khớp Decimal-recompute từ CSV gốc, dùng làm bằng chứng ký "GO" cho phần tài chính trong final go/no-go checklist của nhóm.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Payment domain phải trả lời 2 câu hỏi cho mỗi case: (1) tổng tiền khách đã thanh toán cho order là bao nhiêu, tính từ các payment row có thể nhiều dòng (voucher + credit card nhiều installment...), và (2) số tiền đó có khớp với tổng `item + freight` của order trong ngưỡng sai số cho phép hay không — vì kết quả này quyết định trực tiếp 2 trong 6 nhánh `EC_POLICY_V1` (`valid_split_payment`, `unsupported_late_claim`) và là input bắt buộc để Policy Agent tính refund đúng cho 4 nhánh còn lại.

### Cách triển khai

- Mọi giá trị tiền được parse qua `Decimal(str(x))` rồi `quantize(Decimal("0.01"), ROUND_HALF_UP)` — không bao giờ dùng `float` để tránh sai số nhị phân khi so sánh tolerance.
- `payment_total_brl` = tổng `payment_value_brl` của từng payment row. Điểm mấu chốt (và cũng là bẫy lỗi phổ biến nhất): `payment_value_brl` đã là **toàn bộ** số tiền của dòng đó, **không** phải giá trị từng kỳ trả góp — nên tuyệt đối không nhân với `payment_installments`. Đã viết test chuyên biệt bắt lỗi này (`test_never_multiplies_by_installments`, `test_output_uses_decimal_derived_totals_not_multiplied_by_installments`).
- `reconciliation_delta_brl = |payment_total_brl - reference_order_total_brl|`, với `reference_order_total_brl = item_total_brl + freight_total_brl` (đọc từ `olist_order_items_dataset.csv`, độc lập không phụ thuộc OrderSeller Agent vì Coordinator gọi 3 domain agent song song, không có thứ tự phụ thuộc).
- `is_reconciled = (delta <= 0.10)` — inclusive. Đây là quyết định kỹ thuật quan trọng nhất, giải thích ở mục 5.
- Evidence ID dựng theo đúng format README: `payment:<order_id>:<payment_sequential>`, chỉ tạo từ payment row có thật, sort theo `payment_sequential` tăng dần.
- `PaymentAgent` là lớp mỏng bọc 3 hàm tool (`get_order_payments`, `get_order_financial_reference`, `reconcile_payments`) + tool allowlist guard (`validate_tool_access` raise `PermissionError` nếu gọi tool ngoài danh sách) + system prompt mô tả rõ 6 quy tắc, theo đúng pattern `DeliveryAgent` (TV4) để nhất quán trong repo.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `HandoffEnvelope` (`TASK_REQUEST`) chứa `claimed_order_id`; `data/olist_order_payments_dataset.csv`, `data/olist_order_items_dataset.csv` |
| Output | `PaymentFacts` (`src/contracts.py`): `payments[]`, `payment_total_brl`, `payment_count`, `reconciliation_delta_brl`, `is_reconciled`, `evidence_ids` |
| Module phụ thuộc | Không phụ thuộc module nào khác (đọc CSV trực tiếp, độc lập với OrderSeller/Delivery Agent) |
| Module sử dụng output | `Coordinator._fan_out_domains` (ráp vào `InvestigationBundle.payment`); `Policy Agent`/`Verifier` (qua field tương ứng trong bundle) |
| Điều kiện lỗi cần xử lý | Order không có payment row nào → `payment_count=0`, `payment_total_brl=0.00`, `evidence_ids=[]` (không suy diễn evidence không tồn tại); thiếu `claimed_order_id` trong payload → raise `ValueError` |

### Cách xác minh

```bash
.venv/Scripts/python.exe -m pytest tests/test_finance.py tests/test_payment.py tests/test_payment_agent.py tests/test_financial_audit.py tests/test_cp4_financial_recompute.py -v
.venv/Scripts/python.exe scripts/audit_financials.py
```

- **Kết quả mong đợi:** toàn bộ test pass; script in ra `cases_with_findings: 0`.
- **Kết quả thực tế:** đúng như mong đợi — 5 file test tổng cộng pass hết (finance 10, payment tools 10, payment agent 6, financial audit CP3 3/6 subtest, CP4 recompute 7 test trên 50 case), script CP5 báo `cases_audited: 50, cases_clean: 50, cases_with_findings: 0`. Full suite dự án: 130 passed.
- **Artifact/log:** `docs/checkpoints/tv3-cp0.md` .. `tv3-cp5.md`, `docs/checkpoints/tv3-financial-audit-summary.md`, `logging/tv3_financial_audit.json`. Không chứa secret (đã kiểm tra không có API key trong bất kỳ artifact nào).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** README chỉ nói "tổng payment khớp tổng item + freight trong sai số 0.10 BRL" nhưng không nói rõ 0.10 BRL có được tính là "khớp" hay không (biên `<=` hay `<`). Đây là quyết định ảnh hưởng trực tiếp đến việc case rơi vào `valid_split_payment` hay bị coi là `mismatch`.
- **Các phương án đã cân nhắc:**
  1. `delta < 0.10` (strict, loại trừ đúng biên).
  2. `delta <= 0.10` (inclusive, biên tính là khớp).
- **Phương án đã chọn:** `delta <= 0.10` (inclusive).
- **Lý do:** hằng số `PAYMENT_TOLERANCE = Decimal("0.10")` đã tồn tại sẵn trong `src/tools/policy_tools.py` (code của TV5, viết trước khi tôi bắt đầu CP1) với cách dùng ngụ ý inclusive; chọn theo hướng này để đồng bộ toàn hệ thống thay vì tạo ra 2 định nghĩa "tolerance" khác nhau giữa Payment Agent và Policy/Verifier Agent — nếu lệch nhau, một domain sẽ báo "reconciled" còn domain khác báo "not reconciled" cho cùng 1 case, gây lỗi khó debug.
- **Bằng chứng quyết định phù hợp:** viết riêng 3 fixture biên (`boundary_delta_0_09`, `boundary_delta_0_10`, `boundary_delta_0_11`) từ CP0, test tự động khẳng định đúng 0.10 → `is_reconciled=true`; ở CP3 đối chiếu độc lập với `verification_tools.py` (TV5) và xác nhận cùng dùng `Decimal("0.10")` + so sánh `<=` — không phát sinh mismatch nào trên 50 case thật ở CP4/CP5.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**
  ```
  error: The following untracked working tree files would be overwritten by merge:
          .gitignore
  Please move or remove them before you merge.
  Updating 7b1dc3b..02fb8c7
  Aborting
  ```
- **Lệnh hoặc bước tái hiện:** `git pull origin main` sau khi tự tạo `.gitignore` cục bộ (chưa `git add`) trong lúc dựng môi trường ban đầu; đồng thời commit `feat: add pj scaffold` trên `origin/main` cũng thêm mới một file `.gitignore`.
- **Nguyên nhân gốc:** file `.gitignore` tôi tạo là untracked, trùng đường dẫn với file `.gitignore` sắp được đưa về từ remote trong cùng lần merge — Git từ chối fast-forward vì sẽ ghi đè file chưa được theo dõi mà không hỏi ý kiến.
- **Cách xử lý:** `mv .gitignore .gitignore.mine.bak` (di chuyển tạm, không xoá) → `git pull origin main` chạy được, lấy đúng `.gitignore` + scaffold thật của đồng đội (`src/agents/`, `src/tools/`, `metadata.json`...) → so sánh nội dung 2 bản `.gitignore` → giữ bản của đồng đội (đầy đủ hơn: có `data/processed/`, `.pytest_cache/`...) → xoá file backup.
- **Cách xác minh sau khi sửa:** `git status` → "up to date with origin/main", "nothing to commit, working tree clean"; `git log --oneline -5` xác nhận đã có đủ commit scaffold từ đồng đội.
- **Điều học được:** khi làm việc nhóm trên cùng file cấu hình gốc (`.gitignore`, `requirements.txt`...), nên `git pull` trước khi tự tạo file scaffold cá nhân, thay vì tạo trước rồi mới pull — tránh xung đột untracked-file. Từ đó về sau, mọi checkpoint tôi đều `git status`/`git log` kiểm tra đồng bộ với remote trước khi bắt đầu code.

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của tôi (thay bằng câu hỏi đúng bài Multi-Agent Dispute Resolution, không phải bản mẫu Crossref/vector index không liên quan):

1. **Dữ liệu đi từ CSV Olist đến output JSON như thế nào?** Coordinator nhận `CaseInput` (có `claimed_order_id`), fan-out song song 3 domain agent (OrderSeller, Payment, Delivery) — mỗi agent tự đọc CSV liên quan bằng `order_id`, trả về fact contract riêng (`OrderSellerFacts`/`PaymentFacts`/`DeliveryFacts`). Coordinator gộp thành `InvestigationBundle`, gửi cho Policy Agent để áp `EC_POLICY_V1` ra `PolicyDecision`, rồi Verifier kiểm độc lập (recompute policy + kiểm schema/evidence/financial) trước khi Coordinator ghi `output/EC_xxx.json`.
2. **Evidence ID và root-cause code dùng để đánh giá độ chính xác ra sao?** Mỗi fact phải kèm evidence ID dựng đúng format (`order:`, `item:`, `payment:`, `seller:`, `policy:`) trỏ tới dòng dữ liệu có thật; Verifier tra cứu (`evidence_lookup`) để bác bỏ evidence không tồn tại — đây là cơ chế chống "agent bịa dữ kiện" thay vì chỉ tin lời model.
3. **Ngoài kiểm tra tài chính, còn quality check nào khác trong luồng?** Verifier còn kiểm schema (enum, giới hạn số lượng ID/evidence/action, format ID), tính nhất quán policy (cause/action/status/party đúng với `primary_issue`), và `validate_metadata` (mọi agent phải khai model ≤10B có nguồn xác minh, nếu không sẽ hard-fail khi khởi động).
4. **Vì sao phải dùng cùng tolerance/rounding rule (Decimal, 0.10 BRL) xuyên suốt Payment/Policy/Verifier?** Vì 3 module này tính lại cùng một phép so sánh tài chính ở 3 nơi độc lập (đã xác nhận ở CP3); nếu định nghĩa tolerance lệch nhau dù chỉ 1 cắc, một domain sẽ nói "khớp" còn domain khác nói "không khớp" cho cùng 1 case, khiến Verifier reject nhầm case đúng hoặc chấp nhận nhầm case sai — đó là lý do tôi chủ động đối chiếu 3 implementation ở CP3 thay vì chỉ tin code của mình.
5. **"Thành công" của case được đánh giá dựa trên artifact và metric nào?** Case chỉ tính là thành công khi: output JSON đúng schema, `Verifier.valid=true` (không lỗi FINANCIAL_*/POLICY_*/EVIDENCE_*/SCHEMA_*), trace có đủ invocation của cả 6 agent, và (theo phần audit của tôi) mọi số tiền trong `financial_resolution` khớp lại được từ CSV gốc bằng Decimal — không chỉ dựa vào việc pipeline tự báo "verified".

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Anh Thư
**Ngày xác nhận:** 2026-08-05
