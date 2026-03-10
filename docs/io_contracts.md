# Agent I/O Contracts

## RunConfig (Supervisor output)
- `goal`, `scan_interval_sec`, `monitor_interval_sec`, `report_interval_sec`
- `risk.daily_loss_limit`, `risk.per_trade_limit`, `risk.max_positions`, `risk.cooldown`

## TradePlan / Strategist Output
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
  - `candidates[]`
  - `candidate_count`
  - `candidate_hints[]`
  - `strategic_answers`
  - `source`
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
