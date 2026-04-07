# Runtime Entrypoint Unification

## Goal

- make one file the official trading runtime entrypoint
- keep legacy launchers as compatibility wrappers
- make Commander ownership visible at the runtime entry surface

## Official Entrypoint

- trading runtime:
  - `scripts/run_session.py`
- operator UI:
  - `scripts/start_operator_ui.ps1`
  - `scripts/stop_operator_ui.ps1`

## Supported Commands

- live intraday:
  - `python scripts/run_session.py --mode live --phase intraday`
- live preopen:
  - `python scripts/run_session.py --mode live --phase preopen`
- live closeout:
  - `python scripts/run_session.py --mode live --phase closeout`
- live watch:
  - `python scripts/run_session.py --mode live --phase watch`
- mock intraday:
  - `python scripts/run_session.py --mode mock --phase intraday`
- mock preopen:
  - `python scripts/run_session.py --mode mock --phase preopen`
- mock closeout:
  - `python scripts/run_session.py --mode mock --phase closeout`

## Routing Intent

- `run_session.py` is the only operator-facing trading runtime entrypoint.
- phase selection is explicit:
  - `preopen`
  - `intraday`
  - `closeout`
  - `watch`
- Commander remains the orchestration owner:
  - live `preopen` / `closeout` route through commander runtime once
  - live `intraday` uses the existing loop backend, which still executes commander-aware integrated-chain cycles
  - mock `preopen` / `closeout` keep the existing mock exam orchestration backend
  - watch remains reporting-only

## Compatibility

- existing session `.bat` files remain available as thin wrappers.
- generated dated PowerShell launchers under `reports/runtime/` remain ops convenience wrappers.
- `scripts/run_m13_live_loop.py` remains the intraday loop backend.
- `scripts/run_mock_exam_day.py` remains the mock orchestration backend for preopen and closeout reporting.

## Non-Goals

- no UI consolidation
- no report path migration
- no `reports/trades/*` structure change
- no strategy or execution semantics change
