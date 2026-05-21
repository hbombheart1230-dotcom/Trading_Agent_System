# 2026-05-21 Post-Exit Shadow Recap Closeout Fix

## Problem

`ai_trade_summary.md` could keep `+60m` as pending after the 15:20 and 16:00 recap runs.

Observed case:

- Trade: `TRD_20260521_034220_02`
- Exit time: 2026-05-21 14:43:35 KST
- `+60m` target: 2026-05-21 15:43:35 KST
- Regular-session minute data ended at 15:30 KST

The recap only used cached state rows. If the cache stopped before a mature checkpoint, or if the checkpoint target was after the regular close, the summary could not advance.

## Patch

- `libs/reporting/post_exit_shadow_recap.py`
  - Fetches fresh `market.minute_ohlcv` rows when cached minute rows do not reach a matured pending checkpoint.
  - Merges fresh rows with cached rows by timestamp.
  - Keeps same-day/regular close filtering to avoid T+1 drift.
  - Treats checkpoints maturing after the regular session close as observed at the regular close price, with `closeout_substitute=true`.

- `graphs/commander_runtime.py`
  - Uses a separate runtime key for the 16:00 closeout recap:
    `closeout_guard_after_sweep_1600_final`
  - Prevents an earlier closeout sweep from suppressing the final recap.

## Verification

- `venv\Scripts\python.exe -m pytest tests\test_post_exit_shadow_recap.py tests\test_trade_summary_symbol_metadata.py tests\test_quant_tactic_report.py`
  - Result: 20 passed

- Re-ran:
  - `venv\Scripts\python.exe scripts\run_post_exit_shadow_recap.py --day 2026-05-21 --json`

Result for `TRD_20260521_034220_02`:

- `+60m`: 14,740 (-0.27%)
- `EOD`: 14,740 (-0.27%)
- `fresh_minute_fetch.ok`: true
- `+60m.closeout_substitute`: true

## Close Review Addendum

After the close, two reporting integrity issues were also fixed:

- Added `006345` fallback metadata:
  - Name: `대원전선우`
  - Themes: `전선`, `전력설비`, `구리`
- Replaced mojibake Korean labels in post-exit recap markdown renderers with clean UTF-8 Korean literals.

Verification:

- `TRD_20260521_006345_01` now renders as `006345 (대원전선우)` with symbol themes.
- `post_exit_shadow_recap.md` now reads correctly when decoded as UTF-8.
