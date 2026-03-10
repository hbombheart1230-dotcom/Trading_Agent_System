# Agent I/O Contracts

## RunConfig (Supervisor output)
- `goal`, `scan_interval_sec`, `monitor_interval_sec`, `report_interval_sec`
- `risk.daily_loss_limit`, `risk.per_trade_limit`, `risk.max_positions`, `risk.cooldown`

## TradePlan / Strategist Output
- `themes[]`
- `candidates[]` (Top-N, optional hint/fallback path)
- `strategist_output`
  - `themes[]`
  - `candidates[]`
  - `candidate_count`
  - `source`
- `scenarios[]` (optional)
- `feature_requests[]` (optional)
- `constraints` (optional)

## ScanResult / Scanner Output
- `ranked[]` (`scan_results`)
- `selected` (Top-1 row)
- `top_stock`
- `scanner_candidate_pool` (candidate-source observability metadata)
- `scanner_output`
  - `top_stock`
  - `score`
  - `risk_score`
  - `confidence`
  - `candidate_count`
  - `candidate_source`
  - `theme_filter_applied`
- `data_gaps[]` (optional)

## OrderIntent (Monitor output -> Supervisor input)
- `intent_id`
- `symbol`, `side`, `type(limit/market)`, `qty`, `price`, `tif`
- `reason`, `rationale`, `signal_source`
- `position_age_sec` (when available)
- `risk_check_inputs` (entry/stop/expected_loss/position_size_after)

## SupervisorDecision
- `intent_id`
- `approve | reject | modify`
- `why`
- `modifications` (optional)
