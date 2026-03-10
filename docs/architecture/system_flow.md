# Trading Agent System - System Flow

## Integrated Chain Flow

1. Strategist
   - consumes global/news/sentiment context
   - outputs `themes` + `candidates` (Top-N)
2. Scanner
   - evaluates strategist candidates only
   - computes scores/features/risk
   - outputs `selected` and `top_stock`
3. Monitor
   - entry/exit monitoring for selected stock only
   - emits `OrderIntent` (BUY/SELL/NOOP)
4. Supervisor
   - applies approval + policy checks
5. Executor
   - executes only approved intents with guard precedence
6. Reporter
   - generates operator-facing summaries from logs/artifacts

## Pipeline Role

- `graphs/pipelines/*`: when and in what order nodes run.
- `graphs/nodes/*`: node-level state transformation.
- `libs/*`: reusable pure/domain logic.

## Runtime Notes

- Polling runtime (`scripts/run_m13_live_loop.py`) remains loop-based.
- Guardrails are enforced in execution stage (`execute_from_packet`).
- Sell timing protections are applied in monitor/decision logic:
  - `MIN_HOLD_SECONDS`
  - `SELL_COOLDOWN` or `SELL_COOLDOWN_SEC`
  - `MONITOR_EXIT_CONFIRM_TICKS`
