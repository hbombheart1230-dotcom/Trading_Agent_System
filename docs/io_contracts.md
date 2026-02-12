# Agent I/O Contracts (Draft)

## RunConfig (Supervisor output)
- goal, scan_interval_sec, monitor_interval_sec, report_interval_sec
- risk: daily_loss_limit, per_trade_limit, max_positions, cooldown

## TradePlan (Strategist output)
- candidates[]
- primary
- scenarios[]
- feature_requests[]
- constraints

## ScanResult (Scanner output)
- ranked[]
- recommended_primary
- data_gaps[]

## OrderIntent (Monitor output → Supervisor approval)
- intent_id
- symbol, side, type(limit/market), qty, price, tif
- reason + signals
- risk_check_inputs (entry/stop/expected_loss/position_size_after)

## SupervisorDecision
- intent_id
- approve / reject / modify (+ modifications)
- why
