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
- `entry_participation_control_2026-04-27.md`
- `market_representative_guard_2026-04-28.md`
- `duplicate_buy_and_closeout_guard_2026-04-29.md`
- `daily_profit_guard_policy_draft_2026-05-11.md`
- `../runtime_entrypoint/strategy_conservatism_review_2026-04-29.md`

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
  - applies conservative `entry_policy_delta`, first-pass `hold_policy_delta`, and first-pass `exit_policy_delta`
  - surfaced in monitor artifacts and strategist visibility
- `commander_memory_application_trace`
  - surfaced by scanner and monitor runtime outputs
  - surfaced in canonical scanner/monitor artifacts
  - records whether Commander-approved memory bias was captured, enabled, applied, or skipped
  - records selected scanner symbol/source deltas and monitor entry/hold/exit deltas
- `commander_memory_policy` now uses packet support context directly
  - `route_source`
  - `report_focus_targets`
  - `scanner_status`
  - `monitor_status`
  - `regime observation`
  when deciding whether weekly/monthly layers are active enough to matter
  and when surfacing top-level `policy_signals`
- session closeout buy-block now backfills `minutes_to_close` from runtime KST clock
  - Commander closeout fast-path no longer depends on prepopulated `market_context.minutes_to_close`
  - Monitor closeout window guard uses the same runtime-clock fallback, so post-15:20 BUYs are blocked even when market context is sparse
- session closeout clock now overrides stale `market_context.minutes_to_close` when a reliable runtime clock is present
  - stale upstream values are retained only when no `tick_ts`/runtime clock is available
  - corrected values record the previous value/source for later audit
- execution now has a recent same-symbol BUY guard
  - accepted BUY orders are recorded before portfolio reflection catches up
  - repeated same-symbol BUYs are blocked during the reflection window with `duplicate_buy_recent_order_exists`
  - accepted SELLs clear the same-symbol recent BUY guard record

## Entry Participation Control

Commander owns the entry participation decision when repeated monitor blocks occur:

- If market context is supportive (`risk_on` or `neutral`, no stress/degrade/preflight block) and the same expandable blocker repeats, Commander emits `entry_control.mode=expand_when_market_ok`.
- `expand_when_market_ok` expands monitor runner-up search beyond the default Top-5 and raises scanner scan aggressiveness; for repeated VWAP overextension it can also allow a bounded dynamic VWAP entry band.
- If the market is defensive, blocked, degraded, or an open position is active, Commander emits a preserve mode such as `preserve_defensive_no_trade_ok`, `blocked_no_entry_expansion`, or `position_management_no_entry_expansion`.
- Monitor still owns the final entry gate. Commander expansion only broadens the reviewed pool and, when explicitly allowed, widens the dynamic band; it does not force a BUY.
- A future probe-entry lane should remain Commander-owned. It may allow minimum-size participation under repeated expandable blockers only when cost-adjusted edge, volume, and runtime health are acceptable.
- Probe entry is not a relaxation of hard safety rules. It must be explicitly surfaced as `entry_lane=probe` or equivalent in Commander and Monitor artifacts.

Detailed contract:

- `docs/commander_control/entry_participation_control_2026-04-27.md`

## Market Representative Guard

Commander also owns representative-stock concentration control:

- If Top-1 is a configured market representative such as `005930` or `000660`, and the edge is mostly `top_value` with weak confirmation, Scanner applies a small Commander-authorized penalty.
- Strong theme, volume, momentum, trend, news, or intraday confirmation bypasses the guard.
- This is not a ban list and does not lower entry thresholds. It only prevents trading-value-only near-ties from repeatedly selecting the same broad-market leaders.
- The guard is configured from Commander policy, not environment variables.

Detailed contract:

- `docs/commander_control/market_representative_guard_2026-04-28.md`

## Current Live Validation Snapshot

As of `2026-04-28 12:38 KST`, the latest live canonical commander artifact verifies:

- route: `monitor_only`
- reason: open `000660` position / position-management path
- strategist invocation: skipped for monitor-only path
- Commander-owned scanner fields include `scanner.policy.market_representative_guard`
- Commander horizon policy is present and remains observability-only

Not live-verified in the latest run:

- representative-stock guard application in `scanner.json`, because no fresh scanner pass is emitted while holding
- entry-control expansion in a flat market-supportive state, because the current state is open-position management

Cross-folder status:

- `docs/runtime_entrypoint/current_validation_status_2026-04-28.md`
