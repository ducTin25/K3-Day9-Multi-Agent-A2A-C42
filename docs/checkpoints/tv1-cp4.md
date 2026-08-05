# TV1 CP4 checkpoint

Status: **live run complete**

## Implemented

- Concurrent 50-case batch runner with a configurable limit of 1-16 cases.
- Per-case exception isolation: one failed case is traced and does not stop the batch.
- Atomic writes for verified outputs and the aggregate run summary.
- Reconciliation of received, terminal, verified, written, missing, and unexpected case IDs.
- CLI entry point:

  ```powershell
  .\.venv\Scripts\python.exe -m src.runner --batch --hybrid --write-output --concurrency 4
  ```

- OpenAI-backed entry point for independent Policy and Verifier contexts:

  ```powershell
  .\.venv\Scripts\python.exe -m src.runner --batch --live --write-output --concurrency 2
  ```

## Verification

- Test suite: 118 passed, 49 subtests passed.
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

## Live OpenAI run

- Run ID: `run-a572fa36-1a6e-4b44-a343-7c80d2866ef6`
- Mode: `live_openai`
- Model configured for all agent metadata: `o4-mini`
- Policy and Verifier used separate OpenAI client/context instances.
- Result: 50 received, 50 terminal, 50 verified, 50 written, 0 failed.
- All 50 case-completion trace events are marked `stub: false`.
