# TV1 CP4 checkpoint

Status: **diagnostic ready; final model-backed run pending**

## Implemented

- Concurrent 50-case batch runner with a configurable limit of 1-16 cases.
- Per-case exception isolation: one failed case is traced and does not stop the batch.
- Atomic writes for verified outputs and the aggregate run summary.
- Reconciliation of received, terminal, verified, written, missing, and unexpected case IDs.
- CLI entry point:

  ```powershell
  .\.venv\Scripts\python.exe -m src.runner --batch --hybrid --write-output --concurrency 4
  ```

## Verification

- Test suite: 117 passed, 49 subtests passed.
- Diagnostic run: 50 received, 50 terminal, 50 verified, 50 written, 0 failed.
- Output schema: 50/50 files valid; filenames match their `case_id`.
- Trace: all six logical agents have activity for all 50 cases.
- Primary issue distribution:
  - `canceled_order_paid`: 8
  - `unavailable_order_paid`: 8
  - `late_delivery_seller`: 8
  - `late_delivery_logistics`: 8
  - `unsupported_late_claim`: 9
  - `valid_split_payment`: 9

## Remaining gate

This run intentionally uses the hybrid registry: the three domain agents are integrated,
while Policy and Verifier still use deterministic offline model doubles. Therefore these
artifacts are suitable for CP4 integration diagnostics, but must not be represented as the
final API/model-backed submission run.
