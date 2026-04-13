# Late Session Entry Cutoff Fix (2026-04-11)

## Why this patch exists
On 2026-04-10, successful `000660` BUY executions occurred at 15:23, 15:26, and 15:29 KST even though the runtime already carried `eod_flat_cutoff_min = 10`.

The root cause was not a missing exit threshold. The cutoff existed, but it only influenced the **exit / flatten-before-close** path. There was no matching **entry-side guard** that prevented fresh BUY intents once the session entered the closeout window.

## What changed

### 1. Monitor entry guard now blocks fresh BUY inside the closeout window
`graphs/nodes/monitor_node.py`

A new closeout-window guard resolves:
- `minutes_to_close`
- `use_eod_flat`
- `eod_flat_cutoff_min`

When `minutes_to_close <= cutoff_min` and `use_eod_flat` is enabled, fresh BUY intents are blocked with:
- `entry_guard_reason = buy_blocked_closeout_window`
- `monitor_output.entry_exit_reason = buy_blocked_closeout_window`

This is additive and does not change SELL / EXIT handling.

### 2. Commander prefers a closeout guard posture in the cutoff window
`graphs/commander_runtime.py`

A new session closeout fast-path is used when the runtime is still in `session` phase but the market has already entered the EOD flat window.

Behavior:
- skip strategist/scanner refresh
- avoid new late-session entry generation
- keep monitor/decision/execution available for existing positions
- preserve flatten-before-close behavior for held positions

The runtime path is surfaced as:
- `integrated_chain_closeout_guard`
- `runtime_fast_path.reason = session_closeout_window`

## Observability

### Monitor artifact additions
- `buy_blocked_closeout_window`
- `minutes_to_close`
- `eod_flat_cutoff_min`
- `closeout_window_active`

### Entry blocker surface additions
- `closeout_window_blocked`
- `minutes_to_close`
- `eod_flat_cutoff_min`

### Commander runtime additions
- `session_closeout_guard`
- `runtime_fast_path.reason = session_closeout_window`

## Scope boundaries
This patch only fixes late-session entry behavior.

It does **not** change:
- pullback / breakout / volume gate semantics
- strategist policy
- exit threshold semantics
- ETF exclusion logic
- report/trades artifact layout

## Validation focus
After deployment, the next checks are:
1. No BUY execution after the EOD cutoff window starts.
2. Existing positions still flatten before the close when overnight carry is not approved.
3. `buy_blocked_closeout_window` appears in monitor artifacts for attempted late-session entries.
4. Commander shows `integrated_chain_closeout_guard` / `session_closeout_window` during the closeout window.
