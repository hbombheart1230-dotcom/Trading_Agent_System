# Carry Control Status

Date: `2026-04-20`

## Current Position

Commander-owned carry control is now implemented through the main control path, and the remaining gap is runtime effectiveness validation.

Implemented:

1. carry state surfacing
- `carry_state`
- `carry_risk_bias`
- `session_open_recovery_assessment`

2. commander decision propagation
- surfaced in `commander_open_position_override`
- surfaced in `commander_decision`
- surfaced in `strategist_refresh_context`
- surfaced in `open_position_refresh_context`

3. session posture control
- `urgent_exit_review` can force monitor-only routing
- Commander now shifts:
  - `command_intent`
  - `scanner_mission`
  - `monitor_mission`
  - `flow_instruction`
  toward carry-risk-first handling

4. carry-scoped exit tightening
- Commander now injects carry-specific exit overrides through applied policy
- current override targets:
  - `vwap_break_requires_profit`
  - `hard_stop_pct`
  - `intraday_low_break_pct`
  - `trend_strength_floor`
  - `peak_drawdown_mode` for failed session-open recovery

5. preopen carry review
- preopen phase now seeds open-position override before strategist
- when carry risk is elevated, Commander requests:
  - `strategist_refresh_requested = true`
  - `strategist_refresh_reason = "preopen_carry_risk_review"`
- preopen posture is now allowed to prioritize carry-position review before new entries

## Runtime Entry

Active runtime entrypoint remains:

- `scripts/run_session.py`

Live intraday launch remains:

- `venv\Scripts\python.exe scripts\run_session.py --mode live --phase intraday`

This remains the canonical process boundary.

## 2026-04-20 Runtime Snapshot

Latest operational actions:

- previous live intraday process was stopped
- stale `data/state/m13_live_loop.lock` was removed
- intraday runtime was restarted through the canonical Python entrypoint
- current wrapper process: `508`
- current live child process: `8376`
- current lock owner: `data/state/m13_live_loop.lock -> pid=8376`

Current observed state:

- child process is alive and consuming CPU
- lock heartbeat has advanced after restart
- fresh post-restart `reports/canonical/2026-04-20/...` artifacts are being created

Operational interpretation:

- code restart is complete
- carry-control code is now loaded in the live process
- fresh commander artifacts now confirm that carry-control fields are flowing through live runtime

Latest live observation:

- latest observed carry state: `same_session`
- latest observed carry bias: `normal`
- live artifacts also show earlier `elevated` cases for repeated-hold / loss deterioration
- `urgent_exit_review` has not yet been observed in fresh live artifacts
- `preopen_carry_risk_review` has not yet been observed in today's live artifacts

## Simulation Validation

Because true overnight cases have not yet appeared in fresh live artifacts,
carry-control escalation was also validated through forced simulation/tests.

Validated:

1. commander carry-first routing
- `tests/test_m21_commander_runtime_entry.py`
- `urgent_carry_risk_forces_monitor_only_even_when_buy_not_blocked`
- result: `pass`

2. preopen carry review promotion
- `tests/test_m21_commander_runtime_entry.py`
- `preopen_phase_promotes_carry_risk_review_before_new_entries`
- result: `pass`

3. monitor exit-policy override application
- `tests/test_monitor_exit_guard.py`
- `monitor_exit_policy_prefers_commander_carry_overrides`
- result: `pass`

4. inline forced replay
- simulated state:
  - overnight-approved position
  - session-open reclaim failure
  - weak volume
  - open-position management priority
- observed result:
  - `carry_state = multi_session_stale`
  - `carry_risk_bias = urgent_exit_review`
  - `command_intent = MANAGE_OPEN_RISK`
  - `flow_instruction = REDUCE_CARRY_RISK_FIRST`
  - `runtime_fast_path.reason = holding_position_carry_risk_monitor_only`

Interpretation:

- live artifacts have not yet provided a true overnight urgent case
- but the commander -> monitor carry escalation chain is already verified in controlled simulation
- the remaining gap is live-case effectiveness observation, not implementation coverage

## Immediate Verification Targets

Check these surfaces on the next fresh runtime artifact:

1. `commander.json`
- `carry_state`
- `carry_risk_bias`
- `session_open_recovery_assessment`
- `command_intent`
- `flow_instruction`

2. `strategist.json`
- `commander_context_ref.strategist_refresh_reason`
- `commander_open_position_refresh_context`
- carry-related refresh context fields

3. `monitor.json`
- `effective_exit_policy`
- carry-scoped exit overrides
- whether weak overnight carry gets faster exit review

## Not Implemented Yet

Still pending:

1. scanner ranking/scoring adjustment driven directly by carry bias
2. stronger direct session-open gap model in Commander beyond the current proxy assessment
3. effectiveness validation for true overnight / urgent carry cases in fresh live flow

## Working Rule

Current doctrine is:

- overnight carry is not a simple extra sell rule
- it is a Commander-owned state and posture problem
- monitor remains the executor
- strategist remains the frame/policy proposer
- Commander decides whether the session should prioritize carry-risk management over new exploration

## Current Phase Boundary

This round is complete up to:

1. Commander carry-state derivation
2. Commander carry-first session posture
3. Commander-applied exit-policy tightening
4. preopen carry-risk review before new entries
5. live process restart with the new code loaded

The next phase starts when a fresh runtime artifact proves:

- carry fields are present in `commander.json`
- preopen carry review appears when expected
- monitor sees carry-scoped `effective_exit_policy`
- weak overnight carry is actually reviewed faster in live flow

## Operational Note: Samsung 005930 Was Not A New Carry-Control Proof

The `005930` sell on `2026-04-20` should not be counted as proof of the new Commander carry-control path.

What happened:

- sell run:
  - `reports/canonical/2026-04-20/0b56937a288242bc8da0b24c423b6899`
- exit time:
  - `2026-04-20 10:01:47 KST`
- patched live process restart:
  - after `10:54:15 KST`

Interpretation:

- `005930` exited **before** the patched carry-control runtime restart
- it was already inside the older repeated-hold refresh logic:
  - `override_reason = repeated_hold_monitor_only`
  - repeated hold count was already extreme
- final exit came from existing monitor logic:
  - `exit_reason = intraday_low_break`

So:

- this case proves the older repeated-hold refresh path was active
- it does **not** prove the new Commander-owned carry doctrine in live runtime
