# M8-2 – Decision Packet Contract

## Goal
Define a deterministic interface between "AI decision" and "execution".
There is **no human approval step**.
Execution is always gated by Supervisor.

## Packet
`TradeDecisionPacket = { intent, risk, exec_context }`

- `intent`: what to do (buy/sell/hold) + explicit `order_api_id`
- `risk`: inputs for Supervisor (daily pnl, open positions, cooldown, etc.)
- `exec_context`: parameter values for ApiRequestBuilder

## Nodes
- `graphs/nodes/assemble_decision_packet.py`
  - Produces `state['decision_packet']` for logging and downstream wiring.

## Wiring to execution
Convert packet to `execute_order` state using:
- `TradeDecisionPacket.to_state(catalog_path)`
Or manually map:
- catalog_path, order_api_id, intent, context, risk_context
