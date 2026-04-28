# Kiwoom Truth

## Scope

This folder documents where Kiwoom API data is the authoritative truth source.

Covered areas:

- account cash and holdings truth
- orderable cash truth
- order and fill truth
- day-trade realized PnL truth
- fee/tax truth
- trade-report price and PnL provenance
- Kiwoom theme data used by strategist/scanner

Out of scope:

- runtime memory packet contracts: `docs/runtime_memory`
- report LLM/report canonicalization: `docs/trade_report_plan`
- carry/session posture doctrine: `docs/commander_control`

## Current Principle

1. Kiwoom API values are first-priority truth when available.
2. Last-known broker snapshots may be used only when Kiwoom calls fail.
3. Monitor/local calculations are fallback observations, not broker truth.
4. Reports must expose the source of price, fill, PnL, fee, and tax fields.

## Current Hot Path

Portfolio and holdings:

- Kiwoom endpoint: `kt00018`
- Code:
  - `libs/read/kiwoom_portfolio_reader.py`
  - `graphs/nodes/build_portfolio_snapshot.py`
  - `graphs/nodes/monitor_node.py`

Theme strategist/scanner input:

- Code:
  - `libs/read/kiwoom_theme_reader.py`
  - `graphs/nodes/strategist_node.py`
  - `graphs/nodes/scanner_node.py`
- Contract docs:
  - `kiwoom_theme_strength_packet_2026-04-27.md`
  - `kiwoom_theme_api_strategy_selection_2026-04-28.md`

Order/fill reconciliation:

- Kiwoom endpoints: `kt00007`, `kt00009`
- Current owner code:
  - `libs/read/kiwoom_order_fill_reader.py`
  - `scripts/run_broker_trade_reconciliation.py`

Day-trade realized PnL:

- Kiwoom endpoint: `ka10077`
- Current owner code:
  - `libs/reporting/kiwoom_day_trade_truth.py`
  - `libs/reporting/trade_bundle_assembly.py`

## Current Validation Status

As of `2026-04-28 12:38 KST`:

- Kiwoom theme reader and scanner/strategist theme flow are code/test verified.
- Latest live run is `monitor_only` because `000660` is open; no new broker fill truth was produced in the inspected run.
- Current live artifacts verify position monitoring continues, but do not verify new first-write trade truth.
- See `docs/runtime_entrypoint/current_validation_status_2026-04-28.md` for the full cross-folder matrix.

Tests passed:

- `tests/test_kiwoom_theme_reader.py`
- `tests/test_kiwoom_day_trade_truth.py`
- `tests/test_m31_17_theme_candidate_flow_upgrade.py`

## Remaining Live Checks

1. Next BUY/SELL must confirm first-write live truth is captured before report rendering.
2. Repeated same-symbol `ka10077` rows must select the correct row using symbol/quantity/price/time tie-breakers.
3. Broker truth provenance must appear in `reports/trades/<day>/<trade_id>/reports/ai_trade_report.json`.
4. Theme packet source must distinguish `ok`, unavailable, and fallback states in strategist/scanner artifacts.

## Documents

- `kiwoom_truth_current_state_2026-04-20.md`
- `kiwoom_truth_alignment_plan_2026-04-20.md`
- `kiwoom_scanner_strategist_inventory_2026-04-20.md`
- `kiwoom_role_inventory_2026-04-20.md`
- `kiwoom_theme_strength_packet_2026-04-27.md`
- `kiwoom_theme_api_strategy_selection_2026-04-28.md`
