# Commander Position Management Policy

## Goal

Define when Commander should shift from candidate exploration to position-first
control.

## Principle

Commander is the control owner.

Strategist proposes policy.
Monitor executes policy.
Scanner ranks candidates.

But Commander decides whether the session is primarily:

- `active_selection`
- `position_management`
- `closeout_control`
- `preopen_context`

## Current Baseline

Current runtime already sets:

- `session_bias = position_management` when open positions exist

This is directionally correct, but not yet strong enough for overnight carry and
session-open failure cases.

## Required Upgrade

Commander should not treat all open-position sessions equally.

Instead it should distinguish:

- open positions with healthy recovery
- open positions with carry-risk deterioration
- stale positions that are blocking capital rotation

## Escalation Model

### Level 0

`active_selection`

Use when:

- no open positions
- no carry-risk priority

### Level 1

`position_management`

Use when:

- open positions exist
- but carry deterioration is not yet severe

Effects:

- scanner scope narrows
- monitor prioritizes hold-versus-exit confirmation

### Level 2

`carry_risk_first`

Use when:

- overnight position opens weak
- repeated-hold deterioration accumulates
- active exit axis suggests exit review is overdue

Effects:

- new candidate exploration should be subordinated
- strategist refresh should be preferred
- monitor should use tighter carry-risk-aware exit posture

### Level 3

`urgent_exit_review`

Use when:

- price/pnl anomaly exists
- loss threshold is severe
- recovery quality fails at session open

Effects:

- Commander should prioritize exit review over fresh selection
- scanner should not dominate routing

## Suggested Commander Outputs

Commander decision should eventually surface:

- `session_bias`
- `carry_state`
- `carry_risk_bias`
- `session_open_recovery_assessment`
- `strategist_refresh_requested`
- `strategist_refresh_reason`
- `open_position_refresh_context`

## Example Interpretation

### Ordinary intraday hold

- position opened today
- still above key structure
- no repeated-hold deterioration

Commander result:

- `session_bias = position_management`
- `carry_risk_bias = normal`

### Weak Monday open after Friday carry

- position carried from prior session
- opens weak
- fails VWAP reclaim early
- no convincing recovery

Commander result:

- `carry_state = overnight_open`
- `carry_risk_bias = urgent_exit_review`
- `session_bias` should behave more like carry-risk-first control than ordinary hold

### Multi-session stale carry

- repeated hold cycles accumulate
- active exit axis remains unresolved
- capital is being trapped

Commander result:

- `carry_state = multi_session_stale`
- `carry_risk_bias = elevated` or `urgent_exit_review`
- strategist refresh should tighten carry handling

## Non-Goal

This policy does not make Commander a direct order generator.

Commander remains the control owner, not the execution actor.

Execution still flows through monitor/executor contracts.

