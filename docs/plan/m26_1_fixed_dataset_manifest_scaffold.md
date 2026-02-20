# M26-1: Fixed Dataset Manifest Scaffold

- Date: 2026-02-20
- Goal: establish a deterministic fixed-dataset baseline contract for M26 replay/backtest evaluation.

## Scope (minimal)

1. Define dataset manifest schema and required file layout for M26 fixed dataset v1.
2. Provide one scaffold script that can seed a demo dataset and validate contract compliance.
3. Add regression tests for pass/fail behavior.

## Implemented

- File: `scripts/run_m26_dataset_manifest_check.py`
  - Added fixed schema identifier: `m26.dataset_manifest.v1`.
  - Added required component/file contract:
    - market: `ohlcv_1m/5m/1d`, `corporate_actions`
    - execution: `intents`, `order_status`, `fills`
    - microstructure: `top_of_book`
    - features: `scanner_monitor_features`
    - news: `headlines`, `sentiment_by_symbol`, `sentiment_daily`
  - Added `--seed-demo` mode to scaffold a minimal dataset + manifest.
  - Added validation gate output (`missing_files`, `failures`) and pass/fail exit code (`0`/`3`).

- File: `tests/test_m26_1_dataset_manifest_check.py`
  - Added pass-case test using `--seed-demo`.
  - Added fail-case test for missing manifest/files.

## Safety Notes

- This milestone is read/write only under dataset root; it does not affect runtime trading paths.
- The contract is intentionally minimal and versioned for backward-compatible extension in M26-2+.
