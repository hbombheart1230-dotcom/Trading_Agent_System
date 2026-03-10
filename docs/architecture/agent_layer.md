# Agent Layer

This document defines agent responsibilities and handoff boundaries.

## Goal

- Keep decision and execution responsibilities separated.
- Ensure agents create decisions/intents only.
- Keep all real broker execution inside execution layer with guard precedence.

## Responsibility Split

### Commander
- Orchestrates runtime path and node order.
- Owns transition/state routing and runtime-level events.
- Does not select symbols directly and does not execute broker APIs.

### Strategist
- Builds high-level plan from market/news/global context.
- Emits:
  - `themes`
  - `candidates` (Top-N, optional hint/fallback)
  - `strategist_output`

### Scanner
- Builds candidate universe from Kiwoom market data in integrated chain path.
- Candidate sources:
  - condition search
  - top volume
  - top trading value
  - top change-rate (optional)
- Applies strategist theme/sector filtering when `theme_map` / `sector_map` is available.
- Falls back to strategist candidate hints when Kiwoom pool is empty.
- Produces:
  - `scan_results`
  - `selected`
  - `top_stock`
  - `scanner_output`

### Monitor
- Handles entry/exit logic for selected stock.
- Applies sell protections:
  - `MIN_HOLD_SECONDS`
  - `SELL_COOLDOWN` or `SELL_COOLDOWN_SEC`
  - `MONITOR_EXIT_CONFIRM_TICKS`
- Emits `intents` only.
- Does not execute orders.

### Supervisor
- Evaluates approval/risk policy.
- Can approve/reject/modify before execution.

### Executor / Execution Layer
- Converts approved decision packet into broker request.
- Enforces execution guards and mode safety:
  - `EXECUTION_ENABLED`
  - `ALLOW_REAL_EXECUTION`
  - optional `SYMBOL_ALLOWLIST`
  - size/notional constraints
- Performs the only actual broker call path.

### Reporter
- Derives operator-readable summaries from logs/artifacts.
- Does not alter runtime decisions.

## Runtime Path Notes

- Integrated chain path:
  - Strategist -> Scanner -> Monitor -> Supervisor/Executor
- Legacy live tick path still exists for compatibility (`m10` pipeline).
- `scripts/run_m13_live_loop.py` can select tick pipeline with:
  - `--tick-pipeline legacy_m10`
  - `--tick-pipeline integrated_chain`
  - env `M13_TICK_PIPELINE`
