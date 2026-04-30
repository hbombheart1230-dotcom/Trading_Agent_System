# Trade Report Plan

## Scope

This folder documents the trade-report runtime surface.

Covered areas:

- live closed-trade first-write report generation
- deterministic/manual report regeneration
- LLM report mode boundaries
- trade bundle assembly and lifecycle linkage
- report markdown/JSON readability and provenance
- scanner/strategist/monitor evidence rendering
- operator-facing `ai_trade_summary` artifacts
- summary LLM input/output contract

Out of scope:

- Kiwoom broker truth ownership: `docs/kiwoom_truth`
- runtime memory packet contracts: `docs/runtime_memory`
- Commander runtime doctrine: `docs/commander_control`

## Current Runtime Rule

- `ai_trade_report.*` is the detailed lifecycle/audit report.
- `ai_trade_summary.*` is the operator-facing conclusion/reporting surface.
- In `ai_trade_summary_input.json`, `truth_surface` owns executed prices and realized PnL, while `decision_flow.exit_observation` is only a monitor signal snapshot.
- Live closed-trade first-write should use the report LLM unless explicitly launched in an emergency/no-AI repair path.
- Live closed-trade first-write now also builds `ai_trade_summary_input.json`, calls the summary LLM, writes `ai_trade_summary.json`, and renders the LLM conclusion into `ai_trade_summary.md`.
- Manual regeneration through `scripts/run_ai_trade_report_batch.py` defaults to deterministic/no-LLM for both full report and summary.
- Manual LLM regeneration is opt-in with `--with-llm`; in that mode the report LLM and summary LLM can both run.
- Memory should be derived from deterministic artifacts and explicit memory/application traces, not from prose in `ai_trade_report.md`.
- The summary LLM uses `ai_trade_summary_input.json`, not the full `ai_trade_report.md` prose.
- When the report LLM is used, it should consume structured strategist output directly instead of reconstructing strategy rationale from prose.
- Weekly or multi-day profitability summaries must distinguish order-event coverage from closed-trade PnL-report coverage.
- Cost drag, breakeven move, and cost-adjusted edge should be exposed wherever a trade is evaluated for profitability or future memory feedback.

Primary policy document:

- `report_regeneration_llm_mode_2026-04-25.md`
- `trade_report_summary_llm_contract_2026-04-28.md`

## Current Artifact Set

Per trade:

- `ai_trade_report_input.json`
- `ai_trade_report_compact_input.json`
- `reports/ai_trade_report.json`
- `reports/ai_trade_report.md`
- `reports/ai_trade_report_llm_response.json`
- `reports/ai_trade_summary_input.json`
- `reports/ai_trade_summary.json`
- `reports/ai_trade_summary.md`
- `reports/ai_trade_summary_llm_response.json`

## Current Validation Status

As of `2026-04-28 14:56 KST`:

- Trade-report batch/regeneration and report AI tests are passing.
- Existing `reports/trades/2026-04-28/*/reports` directories contain 19 regenerated `ai_trade_summary_input.json`, `ai_trade_summary.json`, and `ai_trade_summary.md` sets for current closed trades.
- Existing manually regenerated summaries may show summary LLM status `skipped` when regenerated without `--with-llm`.
- Live intraday was restarted after the summary LLM patch, so the next closed trade should exercise the new first-write summary LLM path.
- Summary markdown now separates the normalized exit trigger, monitor observation values, and Truth Surface execution/PnL basis.

Tests passed:

- `tests/test_run_ai_trade_report_batch.py`
- `tests/test_trade_report_ai.py`
- `tests/test_trade_bundle_persistence.py`
- `tests/test_live_execution_bundle_report.py`
- `tests/test_live_execution_bundle_report_runtime_recovery.py`

Remaining live checks:

1. next closed trade must confirm live first-write summary LLM behavior
2. next closed trade must show broker truth provenance from Kiwoom truth surfaces
3. `ai_trade_summary.md` should show `## 🤖 LLM 평가 결론` below operator summary when summary LLM succeeds
4. deterministic regeneration should continue to write skip markers for no-LLM mode
5. `ai_trade_report.md` should remain the detailed report and should not absorb the summary surface
6. next live closed trade should confirm `exit_observation.basis = monitor_signal_snapshot` and Truth Surface price/PnL separation on first write
7. weekly diagnostics should warn when order events exist but closed-trade PnL summaries are incomplete
8. trade summaries should expose whether losses were mostly price movement, cost drag, or exit timing

Cross-folder status:

- `docs/runtime_entrypoint/current_validation_status_2026-04-28.md`
- `docs/runtime_entrypoint/strategy_conservatism_review_2026-04-29.md`
