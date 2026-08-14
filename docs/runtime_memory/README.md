# Runtime Memory Docs

## Goal

This folder defines how runtime memory should be structured and reused across the trading system.

These documents are not limited to trade-report generation.
They cover the memory surfaces that should shape:

- the first strategist pass
- scanner deterministic ranking adjustments
- selected-symbol or long-hold strategist refresh
- future report pruning decisions

## Scope Split

Use `docs/trade_report_plan` for:

- trade report runtime ownership
- report generation guardrails
- report surface pruning
- reporter lane ownership

Use `docs/runtime_memory` for:

- market memory
- symbol memory
- position refresh memory
- retrospective strategist feedback adapters
- future usage matrices and memory flow contracts

## Current Contracts

1. `market_memory_contract_2026-04-19.md`
- pre-selection strategist memory
- current canonical surface:
  - `reports/performance/<day>/strategy_memory.json`
- weekly / monthly commander packets now roll up recent `reports/performance/<day>/strategy_memory.json`
- future richer source / regime aggregates can remain under `reports/performance/*`

2. `symbol_memory_contract_2026-04-19.md`
- scanner deterministic symbol priors
- selected-symbol refresh memory
- current canonical surface:
  - `reports/symbols/<SYMBOL>/symbol_memory.json`

3. `position_refresh_contract_2026-04-19.md`
- long-hold / repeated-hold strategist refresh packet

4. `reports_usage_matrix_2026-04-19.md`
- classifies `reports/*` by runtime role, memory value, and pruning status

5. `strategist_memory_packet_visibility_2026-04-20.md`
- explains where report-derived packets are actually visible in strategist artifacts
- distinguishes:
  - full prompt-payload proof
  - normalized canonical strategist proof
  - empty vs populated `selected_symbol_memory`
- records the current observability gap where some commander refresh runs do not persist matching strategist prompt/canonical artifacts

6. `memory_packet_schema_2026-04-21.md`
- defines the raw runtime packet split:
  - `daily_strategy_memory`
  - `weekly_strategy_memory`
  - `monthly_strategy_memory`
  - `symbol_memory_packet`
- explicitly separates packet structure from commander arbitration and deterministic bias application

7. `operator_summary_memory_linkage_2026-04-28.md`
- defines how operator-facing summary JSON is attached to runtime memory packets
- keeps existing strategy-memory gates and deterministic bias sources intact
- exposes the same curated summaries to strategist prompt context, artifacts, and commander quality diagnostics

8. `memory_integrity_cleanup_2026-07-30.md`
- fixes the authority and unit boundary between canonical performance memory and legacy Reporter feedback
- defines freshness exclusion for legacy qualitative feedback
- separates context visibility from deterministic scanner/monitor delta application in `memory_usage_trace`
- removes package import-order dependence from the runtime-memory test surface

9. `memory_integrity_correction_2026-08-13.md`
- blocks selected-symbol memory from crossing into a different Stage-2 target
- makes daily best/worst playbook guidance evidence-qualified and mutually exclusive
- prevents empty no-trade days from distorting memory windows and freshness
- adds symbol consistency and decision-effect linkage to `memory_usage_trace`

10. `historical_memory_impact_review_2026-08-13.md`
- reclassifies 2026-06-01 through 2026-08-13 Stage-2 calls by memory integrity
- separates clean Strategist/Commander evidence from cross-symbol contamination
- preserves Scanner/Rank-1/offline-alpha findings while narrowing B/C attribution claims

Current additive implementation:

- Commander now surfaces raw memory packets in `commander_decision`
- strategist context/artifacts now surface those packets plus `commander_memory_policy`
- strategist context/artifacts now surface deterministic `memory_usage_trace`
  - records `visible`
  - records `used`
  - records `used=false` reason
  - records symbol `gate_reason`
  - records layer `effect`
  - records scanner/monitor memory-bias application summaries
- weekly/monthly packets now use recent performance-window aggregation
- symbol memory packet now carries richer quality fields:
  - `avg_pnl_pct`
  - `avg_hold_duration_sec`
  - `data_source`
  - `unknown_fields_ratio`
  - `pattern_signal_count`
  - `evidence_strength`
  - `last_trade_date`
  - `recency_days`
- weekly/monthly packets now expose richer structured sections:
  - `window`
  - `sample_quality`
  - `source_performance`
  - `source_context`
  - `failure_patterns`
  - `execution_risk`
  - direct `metrics_<day>.json` route/alignment context
  - direct `reporter_analysis_<day>.json` monitor/scanner/focus context
  - direct `scanner_evaluation.candidate_source_top` / `avg_top_score` / `avg_candidate_pool_after_filter` / `selection_status`
  - `recommended_bias_inputs`
  - `summary_detail`
- daily/weekly/monthly/symbol memory packets now also attach `operator_summary`
  - source:
    - `reports/operator_summary/daily/<YYYY-MM-DD>/daily_summary.json`
    - `reports/operator_summary/weekly/<YYYY-Www>/weekly_summary.json`
    - `reports/operator_summary/monthly/<YYYY-MM>/monthly_summary.json`
    - `reports/operator_summary/symbols/<SYMBOL>/symbol_summary.json`
  - this is a supplemental curated summary surface, not a replacement for `reports/performance/<day>/strategy_memory.json`
  - commander surfaces summary metrics in `layer_quality`, but summary presence alone does not activate scanner/monitor memory bias
- daily operator-summary generation now also refreshes:
  - `reports/performance/<YYYY-MM-DD>/summary.json`
  - `reports/performance/<YYYY-MM-DD>/playbook_stats.json`
  - `reports/performance/<YYYY-MM-DD>/symbol_stats.json`
  - `reports/performance/<YYYY-MM-DD>/strategy_memory.json`
- performance memory now stores pattern-level stats:
  - `per_entry_pattern_stats`
  - `per_exit_pattern_stats`
  - `per_entry_reason_stats`
  - `per_exit_reason_stats`
  - `per_entry_exit_combo_stats`
  - `strategy_memory.pattern_performance_snapshot`
- weekly/monthly activation now depends on packet sample quality, not just packet existence
- symbol override gating is no longer trade-count only:
  - minimum trade/closed-trade history still applies
  - commander now also checks symbol memory data quality and pattern coverage before enabling override
  - commander now also blocks stale symbol memory when last-trade recency exceeds the symbol override age gate
- weekly/monthly packets may still remain inactive until minimum sample-day and confidence gates are met

Current same-day reporter status:

- strategist feedback packet now falls back to same-day `reports/dev/analysis/reporter_analysis/reporter_analysis_<day>.json`
- if same-day metrics are still missing, reporter-analysis blocker totals and recommended actions can still populate `reporter_feedback_packet`
- auto-acceptance now allows blocker-rich same-day reporter-analysis packets even when full route totals are unavailable
- if same-day `metrics_<day>.json` is missing but raw event logs exist, runtime now generates same-day metrics on demand from `data/logs/events.jsonl` before falling back further
- if same-day metrics and reporter-analysis are both missing, strategist feedback can now fall back to closed same-day `reports/trades/<day>/*/reports/ai_trade_report.json` aggregation

Immediate next development order:

1. validate `memory_usage_trace` on fresh live strategist/canonical artifacts
2. validate same-day reporter feedback on live intraday artifacts
3. validate first-pass `monitor_memory_bias` hold/exit application on live artifacts
4. real weekly/monthly source/regime depth beyond current strategy-memory rollup

## Commander Link

Runtime memory packets are raw inputs.

Commander owns memory arbitration.

See:

- `docs/commander_control/commander_memory_authority_2026-04-21.md`
- `docs/commander_control/scanner_memory_bias_2026-04-21.md`
- `docs/commander_control/monitor_memory_bias_2026-04-21.md`

## Existing Adapter Layer

Not every related module is a primary runtime-memory owner.

Current existing adapter of note:

- `libs/reporting/strategy_read_model.py`
  - not broad market memory
  - not symbol-memory canonical storage
  - instead, a retrospective strategist-feedback adapter built from trade-story artifacts
  - used for:
    - trade-story linkage views
    - compact strategist feedback inputs
    - recent strategist feedback windows

## Trade-Level Canonical Surface

`libs/reporting/trade_read_model.py` is now the canonical per-trade read-model owner for:

- deterministic trade facts
- provenance and canonical artifact paths
- normalized runtime context
- normalized report section seeds

`libs/reporting/trade_story_pipeline.py` is the current story-input producer that writes the matching section-seed payloads into trade-story inputs:

- `report_section_seeds`
- `section_provenance.report_section_provenance_seeds`

`libs/reporting/reasoning_trace.py` should treat those same section seeds as canonical fallback summaries before falling back to raw `*_human` blocks.

Current status:

- the `trade_story_pipeline.py -> trade_read_model.py -> trade_report_ai.py` section-seed chain is now aligned at the producer / owner / consumer level
- `trade_report_ai.py` broad regression coverage (`tests/test_trade_report_ai.py`, `tests/test_trade_report_ai_separated_adapter.py`) is currently green after the latest canonicalization pass
- remaining trade-report work should prefer incremental pruning around this canonical chain rather than new sibling adapters

The current section-seed surface exposed through `trade_read_model.context.report_section_seeds` includes:

- `market_context_at_entry`
- `strategist_summary`
- `why_this_symbol_was_chosen`
- `entry_decision`
- `holding_monitoring_story`
- `exit_decision`
- `scanner_filters`
- `execution_quality`
- `guard_approval_result`
- `reporter_evaluation`
- `final_operator_conclusion`

Consumers should prefer this surface over re-normalizing raw:

- `market_context_human`
- `scanner_reason_human`
- `filters_human`
- downstream strategist / entry sections that can be derived from those same normalized inputs

## Current Implementation Direction

The current implementation direction is:

1. strategist pass 1
- read broad market memory from `reports/performance/<day>/strategy_memory.json`

2. scanner deterministic ranking
- read symbol priors from `reports/symbols/<SYMBOL>/symbol_memory.json`
- do not add a scanner LLM

3. monitor execution
- execute inherited policy and deterministic scanner outputs

4. strategist pass 2 refresh
- allowed only after symbol selection or during long-hold / repeated-hold reframe
- consume position-refresh packet and selected-symbol memory excerpt
- do not re-run scanner

5. trade-report adapter
- `libs/reporting/trade_report_ai.py` should consume `trade_read_model` facts/context/section seeds
- section-level provenance should prefer section-seed provenance over legacy raw `*_human` provenance

## Current Symbol-Memory Gate

`symbol_memory_packet` is now quality-gated before it can materially move runtime bias.

Current gate inputs:

- trade count / closed-trade count
- `unknown_fields_ratio`
- `pattern_signal_count`
- `evidence_strength`
- `last_trade_date` -> `recency_days`

Current behavior:

- stale symbol memory is blocked from override
- weak symbol memory may remain present but only as advisory context
- approved symbol memory now scales scanner/monitor symbol-side deltas by evidence strength and recency instead of acting as a simple on/off flag

## Current Hold/Exit Bias Status

`monitor_memory_bias` is no longer entry-only.

Current runtime now applies:

- `entry_policy_delta`
- first-pass `hold_policy_delta`
- first-pass `exit_policy_delta`

Current hold/exit application is intentionally conservative:

- `hold_policy_delta` currently tightens `confirm_ticks`
- `exit_policy_delta` currently tightens:
  - `stop_loss_pct`
  - `take_profit_pct`
  - `trailing_stop_pct`
  - `peak_drawdown_exit_pct`
  - `vwap_breakdown_pct`

Current strength drivers include:

- daily failure patterns
- commander `preferred_risk_posture`
- commander `system_health`
- commander `monitor_status`
- commander `monitor_only_ratio`
- commander `report_focus_targets`
- symbol memory `evidence_strength`
- symbol memory `recency_days`

This is implemented, but still needs live validation before any broader widening.

## Current Conservatism Risk

The `2026-04-29` runtime review shows that current strategist/commander framing is heavily concentrated in defensive mode:

- `playbook=defensive`
- `scanner_bias=leader`
- `require_vwap_reclaim=true`
- `require_rebound=true`

Monitor blocks after the last midday trade were mostly explainable by the active policy, not arbitrary monitor failure. The remaining risk is that memory-driven tightening can reinforce a losing low-frequency loop if it only reduces participation after losses without creating a measured alternate entry lane.

Runtime memory should therefore support two separate outcomes:

- preserve strict gating for normal-size entries when memory and market structure are weak
- allow a separately labeled probe lane only when cost-adjusted edge, liquidity, and symbol-quality gates pass

Do not use memory bias to loosen exits until cost-aware entry quality is visible in fresh artifacts.

## Next Live Validation

On the next live session, verify all of the following on fresh artifacts:

1. same-day `reporter_feedback_packet` uses direct metrics generation when prebuilt metrics are absent
2. strategist artifacts show `reporter_feedback_packet.source_reports.metrics = true` or a justified fallback path
3. monitor artifacts show top-level:
   - `monitor_memory_bias_applied`
   - `monitor_memory_bias_hold_applied`
   - `monitor_memory_bias_exit_applied`
4. `exit_policy_guard_adjustments` records commander-memory hold/exit adjustments
5. symbol-memory reasons show:
   - `symbol_evidence_strength:*`
   - `symbol_recency_days:*`
   when symbol-side damping or blocking occurs

## Current Live Validation Snapshot

As of `2026-04-28 12:38 KST`, the latest inspected monitor-only live artifact verifies part of the memory path:

- `monitor_memory_bias_applied=true`
- `monitor_memory_bias_exit_applied=true`
- `monitor_memory_bias_hold_applied=false`
- Commander horizon policy records memory context for daily and symbol layers
- selected symbol memory for `000660` is visible as an observation, but behavior change remains disabled by horizon policy

Still not live-verified in the latest run:

- fresh strategist `memory_usage_trace`
- same-day reporter feedback packet consumption in a fresh strategist artifact
- scanner-side memory bias in a fresh scanner artifact after the current open position is closed

Cross-folder status:

- `docs/runtime_entrypoint/current_validation_status_2026-04-28.md`
- `docs/runtime_entrypoint/strategy_conservatism_review_2026-04-29.md`
