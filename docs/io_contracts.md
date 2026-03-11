# Agent I/O Contracts

## RunConfig (Supervisor output)
- `goal`, `scan_interval_sec`, `monitor_interval_sec`, `report_interval_sec`
- `risk.daily_loss_limit`, `risk.per_trade_limit`, `risk.max_positions`, `risk.cooldown`

## TradePlan / Strategist Output
- Canonical strategist DTO contract: `libs/strategies/contracts.py::StrategistOutput`
- `market_regime`
- `market_sentiment`
- `key_events[]`
- `themes[]`
- `avoid_themes[]`
- `playbook`
- `scanner_bias`
- `scanner_priority[]`
- `trade_aggressiveness`
- `risk_tone`
- `monitor_guidance`
- `monitor_policy` (derived deterministic guard knobs)
- `report_focus[]`
- `candidates[]` (Top-N, optional hint/fallback path)
- `strategist_output`
  - canonical runtime strategic frame key used by Scanner/Monitor
  - `market_regime`
  - `market_sentiment`
  - `key_events[]`
  - `themes[]`
  - `avoid_themes[]`
  - `playbook`
  - `scanner_bias`
  - `scanner_priority[]`
  - `trade_aggressiveness`
  - `risk_tone`
  - `monitor_guidance`
  - `monitor_policy`
  - `report_focus[]`
  - `regime_score` (additive)
  - `sentiment_score` (additive)
  - `news_context` (additive)
  - `market_context_inputs` (additive)
  - `theme_strength` (additive)
  - `candidates[]`
  - `candidate_count`
  - `candidate_hints[]`
  - `strategic_answers`
  - `llm_frame_status` (`disabled|dry_run|unavailable|ok|parse_error|error`, additive)
  - `llm_frame_applied` (bool, additive)
  - `llm_frame_model` (additive)
  - `source`
- `strategist_llm` (additive runtime snapshot)
  - `status`
  - `model`
  - `applied`
  - `latency_ms`
  - `error`
- `scenarios[]` (optional)
- `feature_requests[]` (optional)
- `constraints` (optional)

## ScanResult / Scanner Output
- `ranked[]` (`scan_results`)
- `ranked_candidates[]` (operator-facing ranked rows)
- `selected` (Top-1 row)
- `top_stock`
- `scanner_candidate_pool` (candidate-source observability metadata)
- `scanner_output`
  - `top_stock`
  - `score`
  - `top_score`
  - `risk_score`
  - `confidence`
  - `candidate_count`
  - `candidate_pool_size`
  - `ranked_candidates` (Top-N summary rows)
  - `candidate_source`
  - `theme_filter_applied`
  - `strategist_playbook` (additive)
- Per-candidate score contract:
  - `score_total`
  - `score_breakdown`
- `data_gaps[]` (optional)

## OrderIntent (Monitor output -> Supervisor input)
- `intent_id`
- `symbol`, `side`, `type(limit/market)`, `qty`, `price`, `tif`
- `reason`, `rationale`, `signal_source`
- `position_age_sec` (when available)
- `position_age_seconds` (alias; when available)
- `monitor_reason` (e.g. `confirmed_exit_signal`, `emergency_exit_signal`)
- `exit_confirm_count` (normal exit confirmation progress)
- `risk_check_inputs` (entry/stop/expected_loss/position_size_after)

## Monitor Exit Observability (`monitor_exit`)
- `triggered`
- `reason`
- `position_age_seconds`
- `exit_signal_detected`
- `exit_confirm_ticks`
- `exit_confirm_count`
- `min_hold_sec`
- `sell_cooldown_sec`
- `min_hold_blocked`
- `sell_cooldown_blocked`
- `monitor_reason`
- `emergency_exit`

## SupervisorDecision
- `intent_id`
- `approve | reject | modify`
- `why`
- `modifications` (optional)

## Minimal Decision Trace / Reason Ledger (additive)
- Runtime keys:
  - `decision_trace_ledger`
  - `reason_ledger` (alias)
- Contract:
  - `run_id`
  - `entries[]`
    - `ts_epoch`
    - `agent` (`strategist|scanner|monitor|supervisor|executor`)
    - `payload` (compact per-agent summary)
  - `latest_by_agent`
- EventLog mirror:
  - `stage=decision_trace`, `event=<snapshot_type>`

## ReporterAnalysis (`reporter_analysis.v1`)
- Passive post-run output generated from logs and derived artifacts.
- Two-layer structure:
  - deterministic baseline analysis
  - optional AI review interpretation on top of deterministic outputs
- Core sections:
  - `trade_summary`
  - `decision_chains`
  - `decision_trace_chain_summary`
  - `strategist_evaluation`
  - `scanner_evaluation`
  - `monitor_evaluation`
  - `supervisor_activity`
  - `intent_flow_analysis`
  - `incident_postmortem`
  - `improvement_suggestions[]`
  - `operator_facing_summary`
  - `developer_facing_summary`
  - `ai_review`
    - `enabled`
    - `status` (`disabled|dry_run|unavailable|ok|parse_error|error`)
    - `model`
    - `reason`
    - `ai_summary`
    - `ai_findings[]`
    - `ai_root_causes[]`
    - `ai_improvement_suggestions[]`
    - `ai_run_grade`
    - `ai_agent_evaluations`
  - top-level convenience aliases:
    - `ai_summary`
    - `ai_findings[]`
    - `ai_root_causes[]`
    - `ai_improvement_suggestions[]`
    - `ai_run_grade`
    - `ai_agent_evaluations`
