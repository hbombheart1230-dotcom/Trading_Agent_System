# 5. Runtime Flow

## 5.1 Integrated Chain Sequence

Operator -> Commander: start_run(goal, config)  
Commander -> Strategist: build strategic brief (regime/sentiment/themes/playbook/guidance)  
Strategist -> Commander: `strategist_output` (`market_regime`, `market_sentiment`, `themes`, `playbook`, `scanner_bias`, `scanner_priority`, `monitor_guidance`, optional `candidates`)  
Commander -> Scanner: build Kiwoom candidate pool, reduce/filter, then score/rank  
Scanner -> Commander: ranked list + score breakdown + `top_stock`  
Commander -> Monitor: evaluate entry/exit for `top_stock`  
Monitor -> Commander: `OrderIntent` (BUY/SELL/NOOP)  
Commander -> Supervisor: approve/reject/modify  
Supervisor -> Commander: `SupervisorDecision`  
Commander -> Executor: execute only if approved  
Executor -> Broker(Mock/Real): place/cancel/status  
Broker -> Executor: order result/status  
Executor -> EventLog: append events  
All key agents -> Decision Trace: append compact per-run reason snapshots (`stage=decision_trace`)  
Commander -> Reporter: generate reports  
Reporter -> Operator: summary

## 5.2 Intent State Machine

(created)  
-> (pending_approval)  
-> (approved | rejected)  
-> (executing)  
-> (executed | failed)  
-> (settled/closed)

Rule: the same `intent_id` must not re-enter `executing`.

Execution note:
- `SYMBOL_ALLOWLIST` is an optional guard. If unset, candidate symbols from Strategist/Scanner are not restricted by allowlist.
- Scanner candidate source defaults to Kiwoom (`CANDIDATE_SOURCE=kiwoom`) with strategist fallback when Kiwoom pool is empty.
- Scanner applies strategist ranking guidance additively (`scanner_priority`, aggressiveness/risk tone).
- Scanner also applies strategist `playbook` additively to ranking weights.
- Scanner can be tuned with: `TOP_CANDIDATE_POOL`, `MIN_TRADING_VALUE`, `MIN_VOLUME`, `ENABLE_THEME_FILTER`, `SCORE_WEIGHTS_*`.
- Monitor normal SELL exits are stabilized by:
  - `MIN_HOLD_SECONDS`
  - `SELL_COOLDOWN` or `SELL_COOLDOWN_SEC`
  - `MONITOR_EXIT_CONFIRM_TICKS`
- Emergency exits (`emergency_halt`, `news_shock`) are explicit separate monitor path.

## 5.3 M13 Tick Runtime Path

- `scripts/run_m13_live_loop.py` supports:
  - `legacy_m10` (default compatibility path)
  - `integrated_chain` (Strategist -> Scanner -> Monitor)
- Control with:
  - CLI `--tick-pipeline`
  - ENV `M13_TICK_PIPELINE`
