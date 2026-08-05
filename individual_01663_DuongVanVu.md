# Bao Cao Ca Nhan - Day 9: Multi-Agent A2A

## 1. Thong Tin Ca Nhan

| Thong tin | Noi dung                                  |
| --- |-------------------------------------------|
| Ho va ten | [Duong Van Vu]                            |
| MSSV | [2A202601663]                             |
| Khoa/Lop | K3                                        |
| Vai tro chinh | TV2 - Data access va Order & Seller Agent |
| Ngay hoan thanh | 2026-08-05                                |

## 2. Vai Tro Va Pham Vi Cong Viec

Vai tro cua toi trong nhom la TV2, phu trach lop truy xuat du lieu Olist lien quan den order, item va seller, dong thoi xay dung `OrderSellerAgent`. Phan nay cung cap su that co the kiem chung cho Coordinator, Delivery, Payment, Policy va Verifier, nhung khong tu quyet dinh refund, primary issue hoac action cuoi cung.

| Module/deliverable | File/ham phu trach | Input | Output | Trang thai |
| --- | --- | --- | --- | --- |
| DP-01 preprocessing | `scripts/preprocess_data.py` | 50 input JSON va CSV Olist | `data/processed/olist_case_index.sqlite`, `manifest.json` | Hoan thanh |
| Repository adapter | `src/data/olist_repository.py` | Raw CSV hoac processed SQLite | `OrderSellerFacts`, schema manifest, evidence lookup | Hoan thanh |
| Order tools | `src/tools/order_tools.py` | `order_id`, processed repository | order/item/seller facts va evidence check | Hoan thanh |
| OrderSellerAgent | `src/agents/order_seller.py`, `src/prompts/order_seller_v1.txt` | `HandoffEnvelope` tu Coordinator | `OrderSellerFacts` dung contract | Hoan thanh |
| Integration audit | `tests/test_tv2_checkpoint3.py`, `tests/test_tv2_checkpoint4.py` | 6 representative cases va 50 official cases | Audit order/item/seller evidence | Hoan thanh |

## 3. Ket Qua Theo Vai Tro

| Nhiem vu | Artifact lien quan | Ket qua | Cach xac minh |
| --- | --- | --- | --- |
| Validate input va tao processed index | `scripts/preprocess_data.py`, `data/processed/manifest.json` | 50 case, 50 unique order IDs, 48 item rows, 60 payment rows | `python scripts\preprocess_data.py` |
| Xay repository doc processed index | `src/data/olist_repository.py` | Lookup duoc order/item/seller cho 50 case | `python -m pytest tests\test_repository.py` |
| Xay OrderSellerAgent | `src/agents/order_seller.py` | Agent chi goi tool order/seller, tra `OrderSellerFacts` | `python -m pytest tests\test_order_seller_agent.py` |
| Tich hop hybrid flow | `src/agents/registry.py` | `order_seller_agent` dung handler that thay stub | `python -m pytest tests\test_tv2_checkpoint3.py` |
| Audit full 50 case | `tests/test_tv2_checkpoint4.py` | 0 mismatch order/item/seller evidence | `python -m pytest tests\test_tv2_checkpoint4.py` |

Output cu the cua phan toi la `OrderSellerFacts`, gom `order_id`, `order_status`, cac timestamp giao hang, danh sach item, `seller_id`, `shipping_limit_date`, `item_total_brl`, `freight_total_brl` va `evidence_ids`.

## 4. Giai Thich Ky Thuat

### Van de can giai quyet

Trong bai toan dispute resolution, loi khach hang dua ra khong du de ket luan. He thong can doi chieu order status, item rows, seller va shipping limit tu CSV Olist. Neu phan order/item/seller sai thi DeliveryAgent co the phan loai sai seller handoff, PaymentAgent co the doi soat sai tong tien, va PolicyAgent co the dua ra refund sai.

### Cach trien khai

Toi tach phan TV2 thanh ba lop:

- Preprocess deterministic: validate schema CSV, parse ID/timestamp/money, loc 50 `claimed_order_id`, tao SQLite index read-only va manifest.
- Repository/tool layer: doc raw CSV hoac processed SQLite, tra facts bang Decimal va timestamp da parse, khong dung geolocation/reviews/products vi policy khong can.
- Agent layer: `OrderSellerAgent` nhan `TASK_REQUEST`, enforce allowlist, goi `lookup_order_seller_facts`, validate bang Pydantic va tra structured output.

Evidence duoc dung truc tiep tu row that:

```text
order:<order_id>
item:<order_id>:<order_item_id>
seller:<seller_id>
```

Neu order khong co item row, agent tra `items=[]`, `item_total_brl=0.00`, `freight_total_brl=0.00` va chi co evidence `order:<order_id>`.

### Input, output va contract

| Thanh phan | Mo ta |
| --- | --- |
| Input | `CaseInput` trong `HandoffEnvelope`, gom `case_id` va `claimed_order_id` |
| Output | `OrderSellerFacts` trong `src/contracts.py` |
| Module phu thuoc | `src/preflight.py`, `src/data/olist_repository.py`, `src/tools/order_tools.py` |
| Module su dung output | Coordinator, Delivery, Payment, Policy, Verifier |
| Dieu kien loi | Missing order, missing seller, duplicate/evidence sai, order khong co item |

### Cach xac minh

```powershell
python -m pytest
```

- Ket qua mong doi: tat ca tests pass, dac biet la TV2 CP3/CP4.
- Ket qua thuc te gan nhat: `105 passed`.
- Artifact/log: `docs/checkpoints/tv2-cp3.md`, `docs/checkpoints/tv2-cp4.md`, `data/processed/manifest.json`.

## 5. Quyet Dinh Ky Thuat Quan Trong

- Boi canh: Can cung cap du lieu sach cho nhieu agent nhung khong muon moi agent doc toan bo CSV hoac suy luan khac nhau.
- Phuong an can nhac: doc raw CSV moi lan agent chay, hoac preprocess thanh SQLite index nho cho 50 order.
- Phuong an da chon: tao `data/processed/olist_case_index.sqlite` va adapter `ProcessedOlistRepository`.
- Ly do: SQLite index giup lookup on dinh, lap lai duoc, co schema ro, evidence lookup doc lap, va giam rui ro moi agent parse CSV khac nhau.
- Bang chung: CP4 audit xac nhan 50/50 order matched, 48 item rows, 40 seller rows, 8 no-item orders, 0 evidence mismatch.

## 6. Loi Hoac Blocker Da Xu Ly

- Trieu chung: Input ban dau co lech ten file, `EC_050` tung nam trong file `input/download`, sau do input duoc normalize lai thanh `EC_050.json`.
- Buoc tai hien: chay `python -m pytest tests\test_preflight.py` tren cac trang thai input khac nhau.
- Nguyen nhan goc: Neu test dua vao ten file nguon thi de fail khi file duoc rename, trong khi logic nghiep vu phai dua vao `case_id` ben trong JSON.
- Cach xu ly: preflight chuan hoa theo `case_id`, output canonical filename la `<case_id>.json`; test tap trung vao `canonical_file`.
- Cach xac minh: `python -m pytest tests\test_preflight.py tests\test_preprocess_data.py`.
- Dieu hoc duoc: Contract nghiep vu nen dua tren truong du lieu co y nghia, khong dua tren ten file tam thoi.

## 7. Hieu Biet Ve Luong End-To-End

1. Runner doc 50 input JSON, validate `case_id`, `claimed_order_id`, policy version va model config.
2. Coordinator nhan tung case va fan-out sang OrderSellerAgent, PaymentAgent, DeliveryAgent bang `HandoffEnvelope`.
3. OrderSellerAgent cua toi tra order/item/seller facts va evidence co the kiem chung.
4. PaymentAgent tra payment rows va reconciliation; DeliveryAgent tra late/not-late va seller handoff violations.
5. Coordinator gom ba domain facts thanh `InvestigationBundle`, gui cho PolicyAgent ap dung `EC_POLICY_V1`.
6. VerifierAgent kiem schema, evidence, financials va policy. Chi khi verify pass thi runtime moi duoc ghi output JSON.
7. Trace can chung minh moi case co invocation rieng cua cac logical agent, khong phai mot prompt duy nhat.

## 8. Cam Ket

- [x] Noi dung bao cao phan anh dung phan viec va muc hieu cua toi.
- [x] Toi co the giai thich luong end-to-end, khong chi module minh phu trach.
- [x] Toi khong ghi da chay thanh cong cho phan chua duoc kiem chung.
- [x] Bao cao khong chua `.env`, API key, token hoac secret.
- [x] Bao cao nay khong phai ban sao nguyen van cua bao cao nhom hoac thanh vien khac.

**Ho va ten:** [Duong Van Vu]

**Ngay xac nhan:** 2026-08-05
