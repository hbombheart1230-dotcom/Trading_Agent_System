# M8-3 – Wiring: Decision Packet → Execution

## Goal
Close the loop so that a single `TradeDecisionPacket` can be executed deterministically:
AI/Strategy → Packet → Supervisor → Executor.

## Node
- `graphs/nodes/execute_from_packet.py`

## Guarantees
- Supervisor approval is mandatory.
- No human/manual approval exists.
- Execution mode is controlled by executor selection (mock/real).
