# 2026-05-14 VWAP Reclaim Strategy And Human Chart Entry Relaxation

## Context

- Today's runtime kept selecting viable candidates, but BUY intent was frequently stopped before execution.
- The dominant monitor blockers were `below_vwap_reclaim_not_ready`, `pullback_below_vwap_reclaim_not_ready`, `pullback_not_mature`, and `volume_confirmation_missing`.
- Most no-trade cycles were near-ready rather than clearly invalid, while the market tape was strong enough that strict VWAP/rebound gating was too conservative.
- The previous tactical label `leader_vwap_reclaim_pullback` also kept strategy reporting anchored to a broad "leader" frame, even when the actual evidence should be classified by setup quality.

## Change

### Strategy Label Replacement

- Replaced new strategist output label:
  - old: `leader_vwap_reclaim_pullback`
  - new: `vwap_reclaim_pullback`
- Kept the old label only as a backward-compatible read alias, so old artifacts or LLM responses normalize into the new label.
- Added/normalized tactical subtypes as evidence classifications:
  - `theme_confirmed_pullback`
  - `market_representative_pullback`
  - `liquidity_confirmed_pullback`
  - `vwap_reclaim_setup`
  - `weak_fallback_pullback`
- Renamed runtime evidence key from `leader_pullback_subtype` to `pullback_evidence_profile`.

### Weak Fallback Gate

- Added a BUY pre-submit quality gate for fallback candidates.
- Rank 4+ fallback candidates are blocked as `weak_fallback_pullback` unless they have at least one real evidence edge:
  - theme confirmation
  - trading-value/liquidity edge
  - volume confirmation plus chart-fit strength
  - top-value plus top-volume confirmation
- This is not a symbol-specific penalty. 005930/000660 are not hardcoded or weighted by name.

### Human Chart Entry Relaxation

- The human-chart layer no longer acts mostly as an extra condition.
- A strong A-grade human-chart setup can now promote near-ready WAIT into BUY when:
  - `entry_quality_score >= 0.78`
  - `transition_readiness_score >= 0.72`
  - volume support is present or near-ready
  - reward room is sufficient
  - exit risk is low
  - there is no strong VWAP breakdown, no high late-entry risk, and no overextension
- The live-promotion chart score threshold was relaxed from the old fixed `0.68` requirement to `0.48` when the broader entry-quality and transition-readiness evidence is strong.
- VWAP reclaim near-ready tolerance for human-chart promotion was widened from `-0.12%` to `-0.25%`.
- Minor misses such as `rebound_ok` and `confidence_ok` can be overridden by an A-grade setup. A clearly failed reclaim or unsafe chart still blocks.

## Safety Rules Kept

- C-grade chart setups do not promote BUY.
- High exit risk blocks promotion.
- Poor candle quality, weak VWAP reference quality, insufficient reward room, or weak multi-window structure blocks promotion.
- Overextended, upper-zone chase, high late-entry-risk, or strong VWAP breakdown contexts remain blocked.
- The executor-side human chart hard guard remains in place.

## Files

- `graphs/nodes/strategist_node.py`
- `graphs/nodes/monitor_node.py`
- `libs/contracts/agent_outputs.py`
- `libs/reporting/strategist_llm_summary.py`
- `libs/reporting/trade_report_ai.py`
- `libs/runtime/intraday_monitor_signals.py`
- `tests/test_monitor_fallback_quality_gate.py`
- `tests/test_intraday_monitor_signals.py`
- related reporting and artifact validation tests

## Validation

- `venv\Scripts\python.exe -m pytest tests\test_monitor_fallback_quality_gate.py tests\test_strategist_frame_llm_integration.py tests\test_phase1_agent_artifact_quality.py tests\test_canonical_artifact_validation.py tests\test_operator_summary_reports.py tests\test_trade_report_ai.py tests\test_trade_story_pipeline_enrichment.py -q`
  - Result: `257 passed`
- `venv\Scripts\python.exe -m pytest tests\test_intraday_monitor_signals.py tests\test_monitor_exit_guard.py tests\test_execute_from_packet.py tests\test_monitor_fallback_quality_gate.py -q`
  - Result: `218 passed`
- `venv\Scripts\python.exe -m pytest tests\test_intraday_monitor_signals.py tests\test_monitor_exit_guard.py tests\test_execute_from_packet.py tests\test_monitor_fallback_quality_gate.py tests\test_strategist_frame_llm_integration.py tests\test_phase1_agent_artifact_quality.py tests\test_canonical_artifact_validation.py tests\test_operator_summary_reports.py tests\test_trade_report_ai.py tests\test_trade_story_pipeline_enrichment.py -q`
  - Result: `470 passed`

## Restart

- Live session restarted after strategy label replacement:
  - `ok=True`
  - `session_pids=[13360, 9540]`
  - stderr size `0`
- Live session restarted after human-chart entry relaxation:
  - `ok=True`
  - `session_pids=[9456, 15128]`
  - stderr size `0`

## Follow-Up

- Review the next BUY decisions to confirm A-grade human-chart promotion is increasing valid participation without reviving weak fallback entries.
- Regenerate or re-read today's operator summary after more post-patch trades, because pre-patch trades still show the old `leader_vwap_reclaim_pullback` label in historical artifacts.
- If weak entries increase, tighten the promotion path by requiring stronger reward-room percent or volume confirmation, not by reintroducing symbol-name penalties.
