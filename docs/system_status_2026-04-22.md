# System Status 2026-04-22

## Scope

This document records the current status, remaining validation, and remaining development work for the active documentation/workstreams below.

- `docs/trade_report_plan`
- `docs/kiwoom_truth`
- `docs/runtime_memory`
- `docs/runtime_entrypoint`
- `docs/commander_control`

## Summary

- Almost closed:
  - `docs/trade_report_plan`
  - `docs/kiwoom_truth`
  - `docs/runtime_entrypoint`
- Still active development:
  - `docs/runtime_memory`
  - `docs/commander_control`

## 1. trade_report_plan

Path:
- `docs/trade_report_plan`

Current status:
- `ai_trade_report` factual alignment is largely stabilized.
- Truth surface is visible in both JSON and markdown.
- Cascade fallback narrative is re-anchored to the actually traded symbol.
- Placeholder and mixed English/Korean fallback text has been cleaned up.
- Memory usage and memory application result sections are present.
- At least one live first-saved report has been validated without requiring regeneration.
- `reporter_evaluation` can now use same-day reporter feedback rebuilt from same-day closed trade reports when linked same-day reporter files are absent.

Validated:
- Buy/sell prices
- Realized pnl / pnl pct
- Fee / tax
- Broker truth surface
- Memory application surface
- LLM generation event flow
- Same-day reporter feedback promotion into `reporter_evaluation` on regenerated reports

Remaining validation:
- Verify the next live trade’s first-saved report again without local-debug regeneration.

Remaining development:
- Keep monitoring live first-saved reports for the same-day reporter path; no major structural gap remains in the report builder itself.

Assessment:
- Core `ai_trade_report` work is effectively complete.
- Remaining work is now operational verification, not report-structure development.

## 2. kiwoom_truth

Path:
- `docs/kiwoom_truth`

Current status:
- Kiwoom truth-first execution/report path is largely stabilized.
- Broker buy price, sell fill price, day realized pnl, fee, tax, and orderable cash surfaces are in place.
- Repeated-trade matching and exit truth propagation have been improved.

Validated:
- `broker_buy_price`
- `broker_fill_price`
- `broker_realized_pnl`
- `broker_fee`
- `broker_tax`
- `broker_day_truth_source`
- Propagation into report/truth surface

Important fixes already in:
- Entry-side order capture
- Day-pnl matching improvements
- Exit truth propagation fix for stale lifecycle execution details

Remaining validation:
- Continue checking first-saved live artifacts on new trades.
- Watch for new repeated-symbol edge cases.

Remaining development:
- No major architecture gap remains.
- Only edge-case tightening is expected.

Assessment:
- Main implementation is nearly closed.
- This is now primarily an operational validation track.

## 3. runtime_memory

Path:
- `docs/runtime_memory`

Current status:
- Memory packet surface exists for:
  - `daily`
  - `weekly`
  - `monthly`
  - `symbol`
- Commander-owned memory policy is surfaced.
- `scanner_memory_bias` and `monitor_memory_bias` are visible in report and artifacts.
- Memory usage and memory application surfaces are now visible in trade reports.
- `weekly/monthly` packets now carry richer structured sections:
  - `sample_quality`
  - `source_performance`
  - `source_context`
  - `failure_patterns`
  - `execution_risk`
  - `recommended_bias_inputs`
- Commander now surfaces per-layer quality and sample-thin rationale for weekly/monthly activation.
- weekly/monthly packets now also read direct same-day supporting artifacts:
  - `metrics_<day>.json`
  - `reporter_analysis_<day>.json`
  for route/alignment/focus/status/regime observation enrichment.
- `source_performance` now also reads direct scanner-evaluation fields:
  - `candidate_source_top`
  - `avg_top_score`
  - `avg_candidate_pool_after_filter`
  - `selection_status`

Validated:
- Memory packet visibility in strategist/report artifacts
- Commander memory policy surface
- Scanner memory bias capture
- Monitor memory bias capture
- Commander `policy_signals -> scanner/monitor bias strength` linkage
- Same-day reporter feedback direct metrics bootstrap from raw `events.jsonl`

Remaining validation:
- Observe more live cycles to evaluate whether the current memory deltas improve trade quality.
- Validate same-day reporter feedback entering intraday strategist/report flow under live same-day artifacts.
- Validate first-pass hold/exit bias application on fresh monitor artifacts.

Remaining development:
- Improve real source/regime depth beyond current strategy-memory rollup and reporter-digest inference
- Improve same-day reporter direct-source speed/robustness beyond current on-demand metrics bootstrap

Recent update:
- `reporter_feedback_packet` now falls back to same-day reporter-analysis artifacts when same-day metrics are missing.
- when same-day metrics artifacts are missing, runtime now attempts to generate `metrics_<day>.json` directly from raw `events.jsonl`
- `reporter_feedback_packet` now also falls back to closed same-day trade-report aggregation when same-day metrics and reporter-analysis artifacts are not yet available.
- This closes the packet-builder gap and leaves live timing validation as the remaining step.

Assessment:
- Structure is in place.
- This is still an active implementation track.

## 4. runtime_entrypoint

Path:
- `docs/runtime_entrypoint`

Current status:
- Hot-path runtime entrypoints are largely cleaned up.
- Shared helpers/lock/config/dispatch responsibilities are moved out of scripts.
- Live loop and background generation entry boundaries are much cleaner.

Validated:
- Lock/heartbeat behavior
- Session dispatch boundaries
- Script import boundaries
- Background generation event path

Remaining validation:
- Normal ongoing operational checks only.

Remaining development:
- Non-hot-path cleanup
- General maintainability cleanup
- preopen artifact day labeling should stay on KST day after the UTC-boundary fix

Assessment:
- Operationally sufficient.
- Low priority compared to runtime memory and commander work.

## 5. commander_control

Path:
- `docs/commander_control`

Current status:
- Commander ownership of memory arbitration has been fixed as a system identity rule.
- Carry-control structure is in place.
- Top-pick blocked to runner-up cascade is live.
- Quote-missing runner-up soft-allow is live.
- Entry-side `monitor_memory_bias` is implemented and visible.
- First-pass `monitor_memory_bias` hold/exit application is now implemented.

Validated:
- Runner-up cascade in live trades
- Memory authority belongs to commander
- Memory bias visibility in artifacts/reports
- Same-session hold/loss closeout tightening path
- Session closeout buy-block now backfills `minutes_to_close` from runtime KST clock when `market_context` is sparse

Remaining validation:
- Overnight carry live proof
- Preopen carry review live proof
- More live evidence for scanner/monitor memory bias effectiveness
- Live evidence that hold/exit deltas are applied and remain behaviorally sane
- Next live closeout window should confirm there are no new post-15:20 BUY executions when `market_context.minutes_to_close` is absent

Remaining development:
- Further commander posture tuning after more live evidence
- More granular hold/exit tuning after first-pass live validation

Assessment:
- Core structure is built.
- This is now a mixed validation + targeted extension track.

## Recommended Priority

1. `docs/runtime_memory`
- Real `weekly/monthly` builders
- Same-day reporter feedback timing/linkage

2. `docs/commander_control`
- Live validation first
- Then hold/exit delta expansion if evidence supports it

3. `docs/trade_report_plan`
- Close same-day reporter linkage

4. `docs/kiwoom_truth`
- Operational validation only

5. `docs/runtime_entrypoint`
- Cleanup only

## Practical Interpretation

If a new development cycle starts now:

- Primary development target:
  - `runtime_memory`
- Secondary development target:
  - `commander_control`
- Operational verification targets:
  - `trade_report_plan`
  - `kiwoom_truth`
- Low-priority cleanup target:
  - `runtime_entrypoint`
