# Agents

## Commander
- Orchestrates one full run cycle.
- Routes state between Strategist, Scanner, Monitor, Supervisor, and Executor.
- Handles retry/pause/cancel transitions and runtime mode selection.
- Never sends orders directly.

## Strategist
- Consumes market/news/global context.
- Selects themes/sectors and candidate symbols (Top-N).
- Emits additive strategist contract fields:
  - `themes`
  - `candidates`
  - `strategist_output`

## Scanner
- Evaluates strategist-provided candidates only in the integrated chain.
- Computes feature/risk/confidence scores per candidate.
- Returns ranked list and Top-1 selection:
  - `scan_results`
  - `selected`
  - `top_stock`
  - `scanner_output`

## Monitor
- Focuses on entry/exit only for the selected stock.
- Emits buy/sell/noop intents from policy + position state.
- Applies sell guards (min hold, sell cooldown, exit confirmation).
- Never executes orders.

## Supervisor
- Owns approval and risk policy checks.
- Can approve/reject/modify intents.
- Guard precedence always overrides approval.

## Executor
- Executes approved intents only.
- Applies execution guards (`SYMBOL_ALLOWLIST`, max qty/notional, mode checks).
- Keeps mock/real separation.

## Reporter
- Builds operator-facing summaries from event logs and reports.
- Does not change runtime decisions.
