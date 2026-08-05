# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                                 |
| --------------- | -------------------------------------------------------- |
| Họ và tên       | Nguyễn Nam Anh                                           |
| MSSV            | 01703                                                    |
| Khóa/Lớp        | K3                                                       |
| Vai trò chính   | TV4 — Delivery Agent & Delay Analysis Specialist         |
| Ngày hoàn thành | 2026-08-05                                               |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| CP0 — Delivery fixtures | `tests/fixtures/delivery/*.json` (`on_time`, `seller_late`, `logistics_late`, `missing_timestamp`) | Contract `DeliveryFacts` (`src/contracts.py`) | 4 fixture JSON files, `docs/checkpoints/tv4-cp0.md` | Hoàn thành |
| CP1 — Delivery tools & Comparator | `src/tools/delivery_tools.py` (`get_delivery_timeline`, `get_shipping_limits`, `compare_delivery_timestamps`) | CSV `olist_orders_dataset.csv`, `olist_order_items_dataset.csv` | Tool trích xuất & thuật toán so sánh mốc thời gian ISO; `docs/checkpoints/tv4-cp1.md` | Hoàn thành |
| CP2 — DeliveryAgent & Security Allowlist | `src/agents/delivery.py` (`DeliveryAgent`, `delivery_agent_handler`) | `HandoffEnvelope` (`TASK_REQUEST` từ Coordinator) | Agent xử lý tin nhắn A2A, bọc Tool Allowlist guard; `docs/checkpoints/tv4-cp2.md` | Hoàn thành |
| CP3 — Representative Branches & Integration | `src/agents/delivery.py`, `tests/test_delivery_agent.py` | 3 nhánh giao hàng đại diện (`not_late`, `seller`, `logistics`, `undetermined`) | Tích hợp end-to-end với PolicyAgent & VerifierAgent; `docs/checkpoints/tv4-cp3.md` | Hoàn thành |
| CP4 — 50-Case Output Audit & Triage | `tests/test_delivery_agent.py` (phần audit CP4) | `output/EC_001..050.json` (chạy batch 50 case của TV1) | Audit 8 seller late, 8 logistics late, 9 unsupported late claim cases; 0 undetermined; `docs/checkpoints/tv4-cp4.md` | Hoàn thành |
| CP5 — Delivery Final Audit Sign-off | `tests/test_delivery_agent.py` (phần audit CP5), `docs/checkpoints/tv4-cp5.md` | 50 output JSON files trong `output/` | Báo cáo ký duyệt hoàn tất 100% (GO) cho miền Giao hàng | Hoàn thành |

Tôi nhận 100% ownership cho miền Delivery Agent và các file được liệt kê ở bảng trên. Các miền khác (OrderSeller — TV2, Payment — TV3, Policy/Verifier — TV5, Coordinator/Runtime — TV1) tôi chỉ đọc contract để giao tiếp tin nhắn A2A qua `HandoffEnvelope`, không tự ý chỉnh sửa code nguồn của các thành viên khác.

---

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả và bằng chứng |
| --- | --- | --- |
| Đăng ký Handler vào Registry | TV1 (`src/agents/registry.py`) | Đã phối hợp hỗ trợ TV1 đăng ký `delivery_agent_handler` vào `build_hybrid_handlers`, thay thế stub bằng agent thực tế |
| Đồng bộ Contract HandoffEnvelope | TV5 (`src/agents/policy.py`, `src/agents/verifier.py`) | Đảm bảo payload `DeliveryFacts` trả ra chứa đúng danh sách `violating_seller_ids` và `evidence_ids` có prefix chuẩn (`order:`, `item:`, `seller:`, `policy:`) để PolicyAgent tính đúng refund cước vận chuyển |
| Tối ưu hóa & Gộp bộ test suite | Nhóm chung (`tests/test_delivery_agent.py`) | Gộp các file test nhỏ (`test_delivery.py`, `test_delivery_cp4.py`, `test_delivery_cp5.py`) thành một bộ test suite duy nhất, gọn nhẹ và dễ bảo trì |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Thuật toán so sánh mốc thời gian ISO | `src/tools/delivery_tools.py` (`compare_delivery_timestamps`) | Phân định chính xác 4 trạng thái `seller`, `logistics`, `not_late`, `undetermined` bằng thư viện chuẩn `csv` | `pytest tests/test_delivery_agent.py -k TestDeliveryTools` → 5 test pass |
| DeliveryAgent & Tool Allowlist Guard | `src/agents/delivery.py` (`DeliveryAgent`) | Chặn 100% cuộc gọi công cụ ngoài allowlist (raise `PermissionError` khi gọi tool tài chính/hoàn tiền) | `pytest tests/test_delivery_agent.py -k TestDeliveryAgent` → 6 test pass |
| Audit tự động 50 case batch thực tế | `tests/test_delivery_agent.py` (`TestDeliveryOutputAudit`) | Kiểm thử 50 output files: 8 seller late, 8 logistics late, 9 unsupported late claim, 0 undetermined | `pytest tests/test_delivery_agent.py -k TestDeliveryOutputAudit` → 5 test pass |
| Báo cáo ký duyệt hoàn tất CP0 - CP5 | `docs/checkpoints/tv4-cp0.md` .. `tv4-cp5.md` | Bộ 6 báo cáo chi tiết cho từng Checkpoint của Thành viên 4 | Kiểm tra tồn tại và nội dung trong `docs/checkpoints/` |

**Artifact cụ thể:** `docs/checkpoints/tv4-cp5.md` — Báo cáo nghiệm thu và ký duyệt cuối cùng của Thành viên 4 cho miền Giao hàng, xác nhận 100% case trong tập 50 output đều được phân loại chính xác, bằng chứng hợp lệ và không phát sinh case `undetermined`.

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Miền Giao hàng (Delivery domain) có nhiệm vụ đối soát mốc thời gian giao hàng thực tế (`delivered_customer_at`) với ngày dự kiến giao (`estimated_delivery_at`) và hạn chót bàn giao hàng của Seller (`shipping_limit_date`). Từ đó xác định xem đơn hàng có bị giao trễ hay không, và quan trọng nhất là **bên nào phải chịu trách nhiệm cho sự chậm trễ này**: Seller bàn giao trễ cho hãng vận chuyển hay Đơn vị vận chuyển (Logistics Provider) phát hàng trễ cho người mua.

### Cách triển khai

1. **Trích xuất dữ liệu không phụ thuộc thư viện ngoài**: Sử dụng module chuẩn `csv` đọc trực tiếp `olist_orders_dataset.csv` và `olist_order_items_dataset.csv` để lấy các mốc thời gian ISO 8601.
2. **Thuật toán phân định trễ hạn 2 bước (Two-stage Delay Classifier)**:
   - **Bước 1**: So sánh `delivered_customer_at` với `estimated_delivery_at`. Nếu `delivered_customer_at <= estimated_delivery_at` $\rightarrow$ Đơn hàng giao đúng hạn (`is_late = False`, `late_stage = "not_late"`).
   - **Bước 2**: Nếu giao trễ (`delivered_customer_at > estimated_delivery_at`), tiến hành kiểm tra mốc `delivered_carrier_at` với `shipping_limit_date` của từng item:
     - Nếu tồn tại ít nhất 1 item có `delivered_carrier_at > shipping_limit_date` $\rightarrow$ Trễ do Seller (`is_late = True`, `late_stage = "seller"`), ghi nhận Seller ID vào `violating_seller_ids`.
     - Nếu tất cả item đều được bàn giao cho hãng vận chuyển đúng hạn nhưng người mua nhận trễ $\rightarrow$ Trễ do Vận chuyển (`is_late = True`, `late_stage = "logistics"`).
     - Nếu thiếu mốc thời gian quan trọng $\rightarrow$ Trả về `late_stage = "undetermined"` kèm theo cảnh báo (`warnings`).
3. **Cơ chế Bảo mật Danh mục Công cụ (Tool Allowlist Guard)**:
   `DeliveryAgent` kế thừa từ `validate_tool_access(tool_name)`. Trước khi gọi bất kỳ công cụ nào, agent bắt buộc kiểm tra xem công cụ đó có nằm trong allowlist (`get_delivery_timeline`, `get_shipping_limits`, `compare_delivery_timestamps`) hay không. Nếu phát hiện lệnh gọi công cụ ngoài phạm vi (ví dụ: `get_payments`, `execute_refund`), agent ném ngay `PermissionError`.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| **Input** | `HandoffEnvelope` (`TASK_REQUEST`) chứa `claimed_order_id`; các tệp CSV Olist |
| **Output** | `DeliveryFacts` (`src/contracts.py`): `order_id`, `is_late`, `late_stage`, `violating_seller_ids`, `delivered_carrier_at`, `delivered_customer_at`, `estimated_delivery_at`, `evidence_ids` |
| **Module phụ thuộc** | Không phụ thuộc module khác (đọc trực tiếp CSV Olist) |
| **Module sử dụng output** | `CoordinatorAgent` (gộp vào `InvestigationBundle.delivery`), `PolicyAgent` (dùng để áp quy tắc `SELLER_HANDOFF_AFTER_LIMIT` / `CARRIER_DELIVERED_AFTER_ESTIMATE`) |
| **Điều kiện lỗi cần xử lý** | Thiếu mốc thời gian ISO $\rightarrow$ `late_stage = "undetermined"`; đơn hàng nhiều item với nhiều Seller khác nhau $\rightarrow$ chỉ quy trách nhiệm cho Seller có `shipping_limit_date` bị vi phạm |

### Cách xác minh

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_delivery_agent.py -v
.\.venv\Scripts\python.exe -m pytest
```

- **Kết quả mong đợi:** Toàn bộ test của `test_delivery_agent.py` và toàn bộ test suite của dự án đều PASS.
- **Kết quả thực tế:** `123 passed in 26.14s` (100% test suite dự án đều PASS).
- **Artifact/log:** `docs/checkpoints/tv4-cp0.md` .. `tv4-cp5.md`, `tests/test_delivery_agent.py`. Không chứa bất kỳ API key, token hay secret nào.

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Khi đơn hàng bị giao trễ tới tay khách hàng (`delivered_customer_at > estimated_delivery_at`), cần quyết định phương pháp xác định nguyên nhân gốc rễ để quy trách nhiệm bồi thường khoản cước vận chuyển (`freight_total_brl`).
- **Các phương án đã cân nhắc:**
  1. *Phương án A*: Mặc định quy toàn bộ trách nhiệm giao trễ cho Đơn vị vận chuyển (`logistics_provider`) cho đơn giản.
  2. *Phương án B*: Phân định 2 bước nghiêm ngặt: Ưu tiên kiểm tra mốc bàn giao kho của Seller (`delivered_carrier_at` vs `shipping_limit_date`). Nếu Seller giao trễ cho nhà vận chuyển, lỗi thuộc về Seller (`seller`). Ngược lại, nếu Seller giao đúng hạn mà khách nhận trễ, lỗi thuộc về đơn vị vận chuyển (`logistics_provider`).
- **Phương án đã chọn:** Phương án B (Phân định 2 bước nghiêm ngặt).
- **Lý do:** Phương án B phản ánh chính xác nghiệp vụ thương mại điện tử thực tế, bảo vệ quyền lợi hợp pháp của nhà vận chuyển khi lỗi xuất phát từ khâu chuẩn bị hàng của Seller. Đồng thời giúp PolicyAgent khấu trừ chuẩn xác tiền cước từ đúng đối tượng vi phạm.
- **Bằng chứng quyết định phù hợp:** Đã kiểm thử qua 50 case chạy thực tế trên tập dữ liệu Olist: Phân định chính xác 8 case trễ do Seller (`late_delivery_seller`), 8 case trễ do Nhà vận chuyển (`late_delivery_logistics`), và 9 case bác bỏ khiếu nại do giao đúng hạn (`unsupported_late_claim`), đạt độ chính xác 100%.

---

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Số lượng file kiểm thử bị phân tán qua nhiều Checkpoint (`test_delivery.py`, `test_delivery_cp4.py`, `test_delivery_cp5.py`), gây trùng lặp logic setup và tạo khó khăn cho việc quản lý test suite khi nâng cấp code.
- **Lệnh hoặc bước tái hiện:** Kiểm tra thư mục `tests/` thấy xuất hiện 3 file test riêng lẻ liên quan đến domain Delivery.
- **Nguyên nhân gốc:** Quá trình phát triển từng bước qua các Checkpoint (CP1, CP4, CP5) tự động tạo ra các file test tương ứng mà chưa gộp lại vào tệp chính.
- **Cách xử lý:** Đã tiến hành tái cấu trúc (refactor), gộp toàn bộ các test case từ `test_delivery.py`, `test_delivery_cp4.py`, `test_delivery_cp5.py` vào duy nhất một tệp chuẩn hóa là `tests/test_delivery_agent.py`. Sau đó tiến hành xóa các file phụ thừa và cập nhật đường dẫn kiểm thử trong toàn bộ tài liệu báo cáo `docs/checkpoints/tv4-cp*.md`.
- **Cách xác minh sau khi sửa:** Chạy lệnh `python -m pytest` kiểm tra toàn bộ repository: `123 passed in 26.14s`.
- **Bài học kỹ thuật:** Sau mỗi giai đoạn phát triển (Checkpoint), cần chủ động dọn dẹp các tệp tạm/tệp kiểm thử phân tán để duy trì cấu trúc dự án sạch sẻ và dễ bảo trì.

---

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ CSV Olist đến output JSON như thế nào?**
   `CoordinatorAgent` nhận yêu cầu `CaseInput` (chứa `claimed_order_id`), tiến hành gửi tin nhắn song song (fan-out) tới 3 Agent chuyên biệt: `OrderSellerAgent` (đọc thông tin đơn hàng/seller), `PaymentAgent` (đọc thông tin thanh toán), và `DeliveryAgent` (đọc mốc thời gian giao nhận). Kết quả phản hồi từ 3 Agent được Coordinator hợp nhất thành `InvestigationBundle`. Coordinator gửi bundle cho `PolicyAgent` để đánh giá theo bộ quy tắc `EC_POLICY_V1` đưa ra `PolicyDecision`. Sau đó `VerifierAgent` thực hiện kiểm định độc lập. Cuối cùng Coordinator xuất kết quả ra file `output/EC_xxx.json`.

2. **Evidence ID và root-cause code dùng để đánh giá độ chính xác ra sao?**
   Mỗi nhận định đều phải đi kèm các mã bằng chứng (`evidence_ids`) được định dạng chuẩn (`order:<id>`, `item:<order_id>:<item_id>`, `seller:<id>`, `payment:<order_id>:<seq>`, `policy:<cause_code>`). `VerifierAgent` tra cứu danh sách này để đảm bảo mọi căn cứ đều dựa trên dữ liệu có thật từ CSV, loại bỏ triệt để hiện tượng Agent tự bịa ra thông tin.

3. **Ngoài kiểm tra tài chính, còn quality check nào khác trong luồng?**
   Luồng kiểm định chất lượng còn bao gồm: Kiểm tra định dạng Pydantic Schema, xác minh giới hạn số lượng bằng chứng ($\le 10$), đối soát tính logic giữa `primary_issue`, `ranked_causes`, `resolution_actions` và `responsible_parties`, cũng như kiểm tra tính hợp lệ của metadata Agent.

4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
   Việc sử dụng chung một tập test set tiêu chuẩn cho tất cả các trạng thái giúp đảm bảo tính khách quan và nhất quán trong đánh giá. Điều này cho phép đo lường chính xác hiệu quả của các cơ chế sửa lỗi (repair mechanism) cũng như sự cải thiện về độ chính xác của hệ thống Multi-Agent.

5. **Repair được xem là thành công dựa trên artifact và metric nào?**
   Một ca sửa lỗi (repair) được tính là thành công khi: `VerifierResult.valid == True`, không còn bất kỳ lỗi vi phạm nào thuộc nhóm `POLICY_*`, `FINANCIAL_*`, `SCHEMA_*` hay `EVIDENCE_*`, file JSON đầu ra khớp schema và dấu vết nhật ký (`trace.jsonl`) ghi nhận đầy đủ luồng sửa lỗi liên agent mà không bị gián đoạn.

---

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Nam Anh  
**Ngày xác nhận:** 2026-08-05
