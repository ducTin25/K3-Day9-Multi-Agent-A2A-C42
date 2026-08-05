# TV3 — Checkpoint 5 handoff (Financial audit, đóng gói)

## Trạng thái

`GO` — audit tài chính cuối cùng trên toàn bộ 50 case thật: **0 finding**. Ký xác nhận phần tài chính cho quyết định GO/NO-GO chung của nhóm.

## Artifact sở hữu

- `scripts/audit_financials.py` — recompute script CLI (đúng deliverable "bằng recompute script" trong `team-plan.md` dòng 351): đọc `output/EC_*.json`, đối chiếu độc lập với `data/*.csv` qua `src/finance.py` + `src/tools/payment_tools.py`, ghi:
  - `logging/tv3_financial_audit.json` — report máy đọc, chi tiết từng case.
  - `docs/checkpoints/tv3-financial-audit-summary.md` — **Financial audit summary** (deliverable chính thức của CP5), có bảng outcome, phân bố primary_issue, bảng finding (rỗng nếu sạch), và go/no-go rõ ràng.
- `docs/checkpoints/tv3-cp5.md` — tài liệu này.

Chạy lại bất kỳ lúc nào:

```powershell
.venv\Scripts\python.exe scripts\audit_financials.py
```

Exit code `0` nếu sạch, `2` nếu còn finding (dùng được trong CI/pre-submit gate).

## Kết quả cuối

- **50/50 case audited, 0 case có finding.**
- Phân bố `primary_issue` đúng như TV1 báo ở CP4 (8/8/8/8/9/9).
- Toàn bộ 6 check tài chính (item/freight/payment total khớp CSV, refund đúng nguồn, tolerance 0.10 BRL, rounding 2dp, evidence payment có thật) đều pass trên mọi case.

## Ký xác nhận cho Final go/no-go checklist (mục 8, team-plan.md)

- [x] `item_total_brl + freight_total_brl` đối chiếu đúng payment theo rule phù hợp — xác nhận qua audit script.
- [x] Refund đúng rule: full payment, full freight hoặc 0 — xác nhận qua audit script.
- [x] Money field Decimal, làm tròn 2 chữ số đúng chuẩn.
- [x] Evidence payment (`payment:<order_id>:<seq>`) tồn tại thật trong CSV.

**Financial audit: GO.** Không có case nào cần sửa thêm trước khi nộp.

## Ghi chú bàn giao cho TV5 (đóng gói zip)

Report/summary của tôi nằm ngoài `output/` (`docs/checkpoints/`, `logging/`) — không lọt vào zip nộp bài theo đúng quy định README mục 9 ("chỉ nén `output/`, không đưa file audit vào zip này").
