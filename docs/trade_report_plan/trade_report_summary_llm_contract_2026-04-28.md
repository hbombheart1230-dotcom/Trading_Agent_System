# Trade Report Summary LLM Contract (2026-04-28)

## Decision

Trade report output is now split into two lanes.

- `ai_trade_report.*`: detailed lifecycle/audit report
- `ai_trade_summary.*`: operator-facing decision summary

The LLM evaluation that an operator reads first belongs to the summary lane, not the full report lane.

## Artifact Layout

For each trade:

```text
reports/trades/<day>/<trade_id>/
  ai_trade_report_input.json
  ai_trade_report_compact_input.json
  reports/
    ai_trade_report.json
    ai_trade_report.md
    ai_trade_report_llm_response.json
    ai_trade_summary_input.json
    ai_trade_summary.json
    ai_trade_summary.md
    ai_trade_summary_llm_response.json
```

## Artifact Roles

`ai_trade_report.json`

- Full deterministic/LLM-merged trade report object.
- Preserves truth surface, strategy/scanner/monitor evidence, memory surfaces, timeline, and provenance.
- This is the detailed source for debugging and audit.

`ai_trade_report.md`

- Human-readable detailed report.
- Kept as-is for full lifecycle inspection.
- It should not be shortened into the operator summary.

`ai_trade_summary_input.json`

- Compact deterministic input for summary evaluation.
- Built from `ai_trade_report.json`.
- Contains immutable facts and bounded evidence only:
  - `truth_surface`
  - `same_day_context`
  - `market_and_strategy`
  - `decision_flow`
  - `memory_and_policy`
  - `deterministic_findings`
  - `llm_task`
- `truth_surface` is the authority for buy price, sell price, realized PnL, fees, taxes, and broker truth source.
- `decision_flow.exit_reason` / `decision_flow.exit_trigger` should be a normalized trigger label, not a long prose sentence.
- `decision_flow.exit_observation` is a monitor signal snapshot only. It may contain monitor current price, position average price, peak price, confirm state, and signal-basis PnL, but it must not be treated as broker fill or realized PnL.

`ai_trade_summary.json`

- Structured summary output.
- Contains the deterministic summary input fields plus `llm_evaluation`.
- `llm_evaluation` is limited to:
  - `conclusion`
  - `root_cause`
  - `priority_actions`
  - `risk_notes`
  - `validation_questions`

`ai_trade_summary.md`

- Operator-facing markdown.
- Renders the deterministic operating summary first.
- If `ai_trade_summary.json.llm_evaluation` has content, the markdown inserts `## 🤖 LLM 평가 결론` immediately below `## 🔴 운영 요약`.

`ai_trade_summary_llm_response.json`

- Compact LLM response artifact for the summary evaluation call.
- Used to verify whether the summary LLM was actually called or skipped.

## LLM Boundary

The summary LLM may interpret.

It must not create or modify:

- prices
- pnl / pnl percentage
- fees / taxes
- order facts
- timestamps
- scanner rank / score
- broker truth source

If evidence is weak, it must say validation is required instead of asserting causality.

Prompt guardrails:

- Use only facts inside `ai_trade_summary_input.json`.
- Use `truth_surface` as the immutable source for executed prices and realized PnL.
- Treat `decision_flow.exit_observation.basis = monitor_signal_snapshot` as signal-observation context only.
- Do not print internal key names such as `root_cause_candidates`, `deterministic_findings`, or `decision_flow` in operator prose.
- Do not create placeholders such as `00번.symbol`; use `trade.symbol`.
- Use Korean prose only. Do not leave Japanese/Chinese fragments or untranslated prompt artifacts.
- Validation questions should be actual questions and should end with `?`.

## Live vs Manual Regeneration

Live closed-trade first-write:

- still uses report LLM when enabled
- additionally builds `ai_trade_summary_input.json`
- calls summary LLM from that compact input
- stores `ai_trade_summary.json`
- renders the LLM conclusion into `ai_trade_summary.md`

Manual/batch regeneration default:

```powershell
venv\Scripts\python.exe scripts\run_ai_trade_report_batch.py --day 2026-04-28 --json
```

- no report LLM
- no summary LLM
- writes deterministic `ai_trade_report.*`
- writes deterministic/skipped `ai_trade_summary.*`

Manual/batch LLM regeneration:

```powershell
venv\Scripts\python.exe scripts\run_ai_trade_report_batch.py --day 2026-04-28 --trade-id TRD_20260428_000660_04 --with-llm --json
```

- calls report LLM
- calls summary LLM using `ai_trade_summary_input.json`
- updates `ai_trade_summary.json`
- inserts `## 🤖 LLM 평가 결론` into `ai_trade_summary.md`

## Memory Rule

Do not use `ai_trade_report.md` or `ai_trade_summary.md` prose as memory source.

Memory must come from deterministic artifacts and explicit traces:

- truth surface
- reporter metrics
- memory application surfaces
- scanner/monitor evidence
- execution and lifecycle artifacts

The summary LLM output is for operator interpretation only.

## Current Implementation

Primary code paths:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/trade_bundle_persistence.py`
- `libs/reporting/live_execution_bundle_runner.py`
- `scripts/run_ai_trade_report_batch.py`
- `libs/reporting/single_trade_report.py`

Primary tests:

- `tests/test_trade_report_ai.py`
- `tests/test_trade_bundle_persistence.py`
- `tests/test_run_ai_trade_report_batch.py`
- `tests/test_live_execution_bundle_report.py`
- `tests/test_live_execution_bundle_report_runtime_recovery.py`

Verified on 2026-04-28:

- report/batch/persistence targeted tests passed
- live bundle regression passed with temporary test lock
- runtime recovery regression passed
- live intraday process was restarted after the patch
