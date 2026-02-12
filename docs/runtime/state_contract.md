# State Contract (Runtime)

This document defines the **state dictionary contract** used across all graph nodes and pipelines.

## Core Rule
- Every node:
  - Accepts `state: dict`
  - Mutates or extends it
  - Returns the same `state`
- Pipelines only orchestrate node calls.

## Canonical Keys
- decision_packet
- decision_trace
- market_snapshot
- portfolio_snapshot
- execution
- run_id
- persisted_state

## Example
```python
state = {
  "market_snapshot": {...},
  "portfolio_snapshot": {...},
}

state = decide_trade(state)
state = execute_from_packet(state)
```
