# TV1 — Checkpoint 3 integration handoff

## Trạng thái

`READY` — Coordinator đã nối đủ ba domain agent thật, Policy/Verifier độc lập, production draft assembler, full verification, targeted repair tối đa một vòng và atomic writer.

## Targeted repair

- Đọc `VerifyResult.errors[*].repair_target` và chỉ gọi lại domain agent đích.
- Domain repair dùng `TASK_REQUEST` với cùng run/case/correlation ID và `attempt=1`.
- Sau domain repair, Coordinator rebuild `InvestigationBundle`, chạy lại `POLICY_REQUEST`, draft assembly và `VERIFY_REQUEST` với `attempt=1`.
- Policy repair bỏ qua ba domain agent và chỉ chạy lại Policy → Verifier.
- Runtime không cho retry vượt quá `attempt=1`; vòng repair thứ hai không tồn tại.

Hai scenario tự động đã pass:

1. `payment_agent` repair: OrderSeller/Delivery giữ nguyên một invocation.
2. `policy_agent` repair: cả ba domain agent giữ nguyên một invocation.

## Sáu case Olist đại diện

| Case | Primary issue |
| --- | --- |
| `EC_003` | `canceled_order_paid` |
| `EC_005` | `unavailable_order_paid` |
| `EC_001` | `late_delivery_seller` |
| `EC_009` | `late_delivery_logistics` |
| `EC_004` | `valid_split_payment` |
| `EC_002` | `unsupported_late_claim` |

Cả sáu case chạy qua Coordinator với TV2/TV3/TV4 domain agent thật, TV5 Policy/Verifier boundary, được `VERIFIED` và atomic-write trong thư mục test tạm.

## Lệnh kiểm chứng

```powershell
.venv\Scripts\python.exe -m pytest -q tests\test_runtime_integration.py
.venv\Scripts\python.exe -m pytest -q
```

Không sửa `docs/team-plan.md` trong checkpoint này.

