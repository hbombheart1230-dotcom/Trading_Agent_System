# 5. Runtime Flow

## 5.1 Integrated Chain Sequence

Operator -> Commander: start_run(goal, config)  
Commander -> Strategist: build themes + candidate symbols (Top-N)  
Strategist -> Commander: `strategist_output` (`themes`, `candidates`)  
Commander -> Scanner: score strategist candidates  
Scanner -> Commander: ranked list + `top_stock`  
Commander -> Monitor: evaluate entry/exit for `top_stock`  
Monitor -> Commander: `OrderIntent` (BUY/SELL/NOOP)  
Commander -> Supervisor: approve/reject/modify  
Supervisor -> Commander: `SupervisorDecision`  
Commander -> Executor: execute only if approved  
Executor -> Broker(Mock/Real): place/cancel/status  
Broker -> Executor: order result/status  
Executor -> EventLog: append events  
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

## 5.3 M13 Tick Runtime Path

- `scripts/run_m13_live_loop.py` supports:
  - `legacy_m10` (default compatibility path)
  - `integrated_chain` (Strategist -> Scanner -> Monitor)
- Control with:
  - CLI `--tick-pipeline`
  - ENV `M13_TICK_PIPELINE`
