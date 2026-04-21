# Commander Control

## Scope

This folder defines Commander-owned runtime control doctrine.

Primary scope:

- session bias selection
- open-position priority control
- overnight carry control
- strategist refresh governance
- monitor posture handoff

This folder is not for:

- trade report ownership
- runtime memory packet contracts
- UI/report surface planning

Those remain in:

- `docs/trade_report_plan`
- `docs/runtime_memory`

## Current Documents

- `carry_control_model_2026-04-20.md`
- `commander_position_management_policy_2026-04-20.md`
- `carry_control_status_2026-04-20.md`
- `commander_memory_authority_2026-04-21.md`
- `scanner_memory_bias_2026-04-21.md`
- `monitor_memory_bias_2026-04-21.md`

Commander-specific memory control in this folder assumes the packet schema defined in:

- `docs/runtime_memory/memory_packet_schema_2026-04-21.md`

## Current Position

Commander already controls:

- phase routing
- session bias
- strategist pass-1 invocation
- strategist refresh invocation
- repeated-hold refresh triggering

What still needs to be strengthened:

- scanner narrowing driven directly by carry-risk bias
- stronger direct session-open gap model
- live-effectiveness validation from fresh artifacts

## Current Implementation Status

Implemented additively:

- Commander now derives `carry_state`
- Commander now derives `carry_risk_bias`
- Commander now derives `session_open_recovery_assessment`
- These fields now surface in:
  - `commander_open_position_override`
  - `commander_decision`
  - `strategist_refresh_context`
  - `open_position_refresh_context`
- Commander now tightens session posture when carry risk is elevated:
  - urgent carry risk can force monitor-only routing
  - decision metadata now shifts to carry-first missions and flow instructions
- Commander now applies carry-scoped monitor exit-policy overrides
- preopen can now trigger carry-risk review before new entries
- Commander now surfaces raw memory packets and `commander_memory_policy`
- strategist artifacts now surface commander-owned memory visibility

Not implemented yet:

- scanner ranking/scoring driven directly by carry-risk bias
- stronger direct session-open gap model instead of the current proxy assessment
- live-effectiveness validation from fresh restarted artifacts

Now implemented:

- deterministic `scanner_memory_bias`
  - Commander-owned
  - additive and conservative
  - surfaced in scanner artifacts and strategist visibility
- deterministic `monitor_memory_bias`
  - Commander-owned
  - currently applies conservative `entry_policy_delta` only
  - surfaced in monitor artifacts and strategist visibility
