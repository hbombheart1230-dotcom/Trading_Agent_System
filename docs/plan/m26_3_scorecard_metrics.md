# M26-3: Scorecard Metrics Scaffold

- Date: 2026-02-20
- Goal: add deterministic strategy scorecard outputs over M26 fixed dataset replay data.

## Scope (minimal)

1. Compute PnL proxy (realized/unrealized/total) from fixed dataset `intents` + `fills` + market close.
2. Compute risk-adjusted proxy metrics (Sharpe/Sortino proxies).
3. Compute drawdown metrics from replay equity curve.
4. Add regression tests for pass/fail and positive-PnL scenario.

## Implemented

- File: `scripts/run_m26_scorecard.py`
  - Required input files:
    - `manifest.json`
    - `execution/intents.jsonl`
    - `execution/fills.jsonl`
    - `market/ohlcv_1d.csv`
  - Added scorecard outputs:
    - `realized_pnl_proxy`, `unrealized_pnl_proxy`, `total_pnl_proxy`
    - `win_rate`
    - `risk_adjusted` (`sharpe_proxy`, `sortino_proxy`, `pnl_mean`, `pnl_std`)
    - `drawdown` (`max_drawdown_abs`, `max_drawdown_ratio`, `equity_end`, `equity_peak`)
  - Added `--day` UTC filter and pass/fail return code (`0`/`3`).

- File: `tests/test_m26_3_scorecard.py`
  - Added seeded pass-case test.
  - Added positive realized PnL scenario test.
  - Added missing-files fail-case test.

## Safety Notes

- Scorecard script is read-only over dataset inputs.
- Outputs are analytic-only and do not affect runtime execution paths.
