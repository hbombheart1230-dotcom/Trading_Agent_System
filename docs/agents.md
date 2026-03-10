# Agents

## Commander
- Orchestrates one full run cycle.
- Routes state between Strategist, Scanner, Monitor, Supervisor, and Executor.
- Handles retry/pause/cancel transitions and runtime mode selection.
- Never sends orders directly.
- Canonical implementation: `graphs/commander_runtime.py`
- Compatibility layers:
  - `graphs/nodes/commander_node.py` (thin runtime wrapper)
  - `libs/agent/commander.py` (legacy adapter/scaffolding)

## Strategist
- Consumes market/news/global context.
- Selects themes/sectors.
- May provide candidate hints (Top-N) as an additive signal.
- Emits additive strategist contract fields:
  - `themes`
  - `candidates`
  - `strategist_output`
- Canonical implementation: `graphs/nodes/strategist_node.py`
- Compatibility layer: `libs/agent/strategist.py` (normalizes strategist output for legacy `Plan` usage)

## Scanner
- Uses Kiwoom market data as primary candidate source in integrated chain.
- Candidate sources include condition search, top-volume, top-value, optional top-change-rate, sector/theme map, and operator watchlist.
- Applies theme/sector filtering from strategist output (`themes`) with `theme_map` / `sector_map`.
- Falls back to strategist candidates when Kiwoom candidate pool is empty.
- Reduces candidate pool with practical filters (halted/abnormal/illiquid thresholds).
- Computes practical score factors (trading-value, momentum, trend, volume-surge, intraday strength, penalties).
- Returns ranked list and Top-1 selection:
  - `scan_results`
  - `ranked_candidates`
  - `selected`
  - `top_stock`
  - `scanner_output`
- Canonical implementation: `graphs/nodes/scanner_node.py`
- Compatibility stage helper: `graphs/nodes/scan_candidates.py`

## Monitor
- Focuses on entry/exit only for the selected stock.
- Emits buy/sell/noop intents from policy + position state.
- Applies sell guards (min hold, sell cooldown, exit confirmation).
- Suppresses duplicate SELL intents with pending-exit lock/cooldown state across polling loops.
- Keeps emergency exits (`emergency_halt`, `news_shock`) explicit and separate from normal exit confirmation flow.
- Never executes orders.
- Canonical implementation: `graphs/nodes/monitor_node.py`
- Compatibility interface: `libs/agent/monitor.py` (legacy placeholder)

## Supervisor
- Owns approval and risk policy checks.
- Can approve/reject/modify intents.
- Guard precedence always overrides approval.

## Executor
- Executes approved intents only.
- Applies execution guards (optional `SYMBOL_ALLOWLIST`, max qty/notional, mode checks).
- Keeps mock/real separation.

## Reporter
- Builds operator-facing summaries from event logs and reports.
- Works as a post-run/report script layer (not a runtime control node).
- Does not change runtime decisions.
- Runtime report generators: `libs/reporting/*`, `scripts/run_*report*.py`
