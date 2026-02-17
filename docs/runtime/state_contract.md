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
- resilience
- circuit

## Runtime Resilience Keys (M23-1)
- `state["resilience"]`
  - `contract_version`: `m23.resilience.v1`
  - `degrade_mode`: bool
  - `degrade_reason`: str
  - `incident_count`: int
  - `cooldown_until_epoch`: int
  - `last_error_type`: str
- `state["circuit"]["strategist"]`
  - `state`: `unknown|closed|open|half_open`
  - `fail_count`: int
  - `open_until_epoch`: int
  - `last_error_type`: str

## Example
```python
state = {
  "market_snapshot": {...},
  "portfolio_snapshot": {...},
  "resilience": {
    "contract_version": "m23.resilience.v1",
    "degrade_mode": False,
    "incident_count": 0,
  },
  "circuit": {
    "strategist": {"state": "unknown", "fail_count": 0, "open_until_epoch": 0}
  },
}

state = decide_trade(state)
state = execute_from_packet(state)
```
