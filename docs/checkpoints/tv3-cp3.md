# TV3 — Checkpoint 3 handoff (Financial audit / review chéo)

## Trạng thái

`READY_WITH_FINDINGS` — CP3 của TV3 là review chéo, không phải module mới. Đã audit xong 2 việc trong phạm vi không bị block, tìm ra 1 rủi ro cấu trúc cần cả nhóm biết, và xác nhận vẫn còn 2 blocker tích hợp thuộc TV1 (đã có sẵn từ CP2/CP3 handoff của TV5) khiến chưa thể review trên một run thật.

## Vì sao không tự làm được toàn bộ CP3 ngay

`src/agents/registry.py` (`build_hybrid_handlers`, TV1 sở hữu) hiện chỉ wire `delivery_agent`, `policy_agent`, `verifier_agent` vào handler thật; **`payment_agent` vẫn chạy bằng stub** dù `payment_agent_handler` (CP2 của tôi) đã sẵn sàng. Cộng với 3 blocker TV5 đã báo (`docs/checkpoints/tv5-cp3.md`: chưa có repair loop, chưa nối `assemble_tv5_draft`, chưa có atomic writer), pipeline chưa chạy được end-to-end thật — nên chưa có `output/EC_xxx.json` thật nào để review. Phần này tôi không tự sửa vì thuộc ownership TV1.

Vì vậy CP3 của tôi tập trung vào phần **làm được ngay, không cần chờ ai**: audit độc lập trên contract/dữ liệu đã đóng băng.

## Artifact sở hữu

- `tests/test_financial_audit.py` — 2 audit, 3 test / 6 subtest:
  1. **`TestOrderTotalsCrossCheckWithPaymentDomain`**: so `OrderSellerFacts.item_total_brl/freight_total_brl` (TV2, `src/data/olist_repository.py`) với reference totals tự tính của Payment domain (TV3, `src/tools/payment_tools.py::get_order_financial_reference`) trên 40 order thật có payment. Hai bên đọc CSV **độc lập**, không dùng chung hàm.
  2. **`TestRefundRecomputeAgainstPolicyAgent`**: viết lại từ đầu (không import `policy_tools.py`) hàm suy refund theo đúng bảng 6 rule ở README mục 4, chạy trên cả 6 golden case của TV5 (`tests/fixtures/policy/golden_cases.json`), rồi đối chiếu 3 chiều: kết quả tự tính = `evaluate_policy()` thật của TV5 = giá trị `expected` trong fixture.
- `docs/checkpoints/tv3-cp3.md` — tài liệu này.

## Kết quả audit

- **Order totals TV2 vs TV3**: khớp 100% trên 40 order thật (`item_total_brl`, `freight_total_brl`). Không phát hiện sai lệch số liệu ở thời điểm audit.
- **Refund theo rule**: cả 6 nhánh `EC_POLICY_V1` — recompute độc lập bằng `src/finance.py` khớp tuyệt đối với `evaluate_policy()` của TV5 và với `expected` trong golden fixture.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_financial_audit.py -v
```

Kết quả: 3 passed, 6 subtests passed (~17s). Full suite `pytest -q`: **99 passed**, không còn failure nào.

## Phát hiện cấu trúc cần báo cả nhóm (không phải bug hiện tại, nhưng là rủi ro)

**`item_total_brl` / `freight_total_brl` đang được tính độc lập ở 2 nơi khác nhau**, đọc cùng CSV (`olist_order_items_dataset.csv`) nhưng không dùng chung hàm:

1. `src/data/olist_repository.py::get_order_seller_facts` (TV2) — dùng `_parse_decimal()` (không `.quantize()` từng dòng).
2. `src/tools/payment_tools.py::get_order_financial_reference` (TV3) — dùng `src/finance.py::to_money()` (quantize `ROUND_HALF_UP` mỗi dòng và mỗi lần cộng).

Hôm nay hai bên khớp nhau (giá trị CSV gốc vốn đã đúng 2 chữ số thập phân nên không có gì để làm tròn khác biệt), nhưng **không có nguồn sự thật (single source of truth) chung** — nếu một bên đổi logic (vd. thêm chiết khấu, đổi rounding) sẽ âm thầm lệch mà không ai biết, vì `tests/test_financial_audit.py::TestOrderTotalsCrossCheckWithPaymentDomain` là **test duy nhất** đối chiếu hai bên này.

Ngoài ra: **`PaymentFacts.is_reconciled` / `reconciliation_delta_brl` (Payment domain tự tính, CP1-CP2) hiện không được `output_tools.py` (TV5) sử dụng ở đâu cả** — `financial_resolution.payment_total_brl` trong output cuối chỉ lấy `bundle.payment.payment_total_brl`, còn phép đối soát thật sự (item+freight vs payment, tolerance 0.10) lại được TV5 tính **lại từ đầu** trong `verification_tools.py::_validate_policy_consistency`, không đọc `is_reconciled` của Payment Agent. Không sai (`_validate_policy_consistency` tự đủ đúng, đã audit ở trên), nhưng nghĩa là field `is_reconciled` của Payment Agent hiện là "dead field" trong luồng thật — chỉ có giá trị tham khảo/debug.

**Đề xuất** (không tự sửa vì đụng file người khác, chỉ ghi nhận cho TV1/TV2 quyết định): nếu về sau `item_total_brl`/`freight_total_brl` cần logic phức tạp hơn (chiết khấu, phí phát sinh...), nên gom về một hàm dùng chung thay vì hai implementation song song.

## Blocker cần TV1 xử lý (nhắc lại + bổ sung)

1. **[Mới]** `src/agents/registry.py::build_hybrid_handlers` chưa wire `payment_agent` (và `order_seller_agent`) vào handler thật — vẫn dùng `stub_handlers()["payment_agent"]`. Cần thêm `handlers["payment_agent"] = payment_agent_handler` (từ `src/agents/payment.py`, đã sẵn sàng từ CP2) để pipeline có dữ liệu payment thật.
2. Ba blocker TV5 đã báo ở `tv5-cp3.md` (B1 repair loop, B2 chưa nối `assemble_tv5_draft`, B3 chưa có atomic writer) — vẫn đang chặn "representative cases verified and written" của cả nhóm.
3. Sau khi (1) và (3) xong, TV3 sẽ review lại trên `output/EC_xxx.json` thật thay vì chỉ audit trên fixture/CSV như hiện tại.
