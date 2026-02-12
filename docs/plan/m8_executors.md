# M8-1 – Executors (mock/real)

## Goal
Keep approval logic inside Supervisor and split execution into two concrete executors:
- MockExecutor: no network, no trading (safe)
- RealExecutor: real HTTP call (guarded)

## Key rule
Order execution **always** requires Supervisor.allow() = True.
There is no human/manual approval step.

## Env controls
- EXECUTION_MODE=mock|real (default: mock)
- EXECUTION_ENABLED=true|false (default: false)

## Node
- `graphs/nodes/execute_order.py`
  - Supervisor gate → build PreparedRequest → executor.execute()
