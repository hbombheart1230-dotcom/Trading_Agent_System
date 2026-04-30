# Strategy Conservatism Review 2026-04-29

Snapshot time: `2026-04-29 13:50 KST`

Scope:

- week-to-date runtime from `2026-04-27` through `2026-04-29 13:50 KST`
- mock broker live path using `scripts/run_session.py --mode live --phase intraday`
- trade reports under `reports/trades/<day>`
- canonical runtime artifacts under `reports/canonical/<day>/<run_id>`
- operator event log `data/logs/events.jsonl`

## Executive Finding

The current runtime is not failing because Monitor is arbitrarily blocking trades.

The stronger issue is that Strategist and Commander are repeatedly producing a conservative frame:

- `playbook=defensive`
- `scanner_bias=leader`
- `require_vwap_reclaim=true`
- `require_rebound=true`
- tight VWAP extension and breakout confirmation thresholds

Monitor then applies that frame faithfully. This produces many NOOPs, and when trades do pass, exits are often too sensitive relative to mock broker fee/tax drag.

The result is a poor combination:

- low-quality trade acceptance under conservative confirmation
- fast exits through `peak_drawdown`, `intraday_low_break`, or `hard_stop`
- realized losses dominated by costs and small adverse moves
- long no-trade windows when VWAP/reclaim/breakout gates are not aligned

## Week-To-Date Trade Summary

Event-log order successes:

| Day | BUY | SELL | Total |
| --- | ---: | ---: | ---: |
| 2026-04-27 | 20 | 15 | 35 |
| 2026-04-28 | 29 | 23 | 52 |
| 2026-04-29 | 6 | 7 | 13 |
| Total | 55 | 45 | 100 |

Closed-trade PnL reports available:

| Day | Closed trades | Wins | Losses | PnL | Avg PnL pct |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-04-27 | 0 | 0 | 0 | n/a | n/a |
| 2026-04-28 | 19 | 2 | 17 | -71,986 | -0.3298% |
| 2026-04-29 | 6 | 2 | 4 | -23,992 | -0.3349% |
| Reported total | 25 | 4 | 21 | -95,978 | -0.3311% |

Important coverage note:

- `2026-04-27` has successful order events, but closed-trade PnL summaries were not available in the inspected report surface.
- Any weekly profitability summary must label `2026-04-27` as event-covered but PnL-report incomplete until report/truth reconciliation backfills it.

## Runtime Behavior Summary

Order and block results from `data/logs/events.jsonl`:

- successful broker mock order results: `100`
- blocked/false order results: `301`
- dominant blocked reason: `noop_intent_skipped` (`298`)
- broker rejects: `broker_rejected:20` (`3`)

Monitor reason distribution:

| Reason | Count | Interpretation |
| --- | ---: | --- |
| `buy_blocked_open_position` | 827 | position-management guard active |
| `post_exit_cooldown` | 134 | churn prevention after sell |
| `too_extended_from_vwap` | 113 | entry too far above VWAP |
| `breakout_not_ready` | 84 | breakout confirmation not met |
| `below_vwap_reclaim_not_ready` | 48 | VWAP reclaim not confirmed |
| `entry_wait` | 46 | generic wait/confirmation path |
| `volume_insufficient` | 24 | volume confirmation missing |

Strategist frame distribution from canonical artifacts:

| Field | Dominant value | Count |
| --- | --- | ---: |
| `playbook` | `defensive` | 255 / 258 |
| `playbook` | `breakout` | 3 / 258 |
| `scanner_bias` | `leader` | 255 / 258 |
| `scanner_bias` | `momentum` | 3 / 258 |
| `strategist_llm.result` | ok | 255 |
| `strategist_llm.result` | error | 1 |

This shows a strategy-frame concentration problem, not an LLM availability problem.

## 2026-04-29 Intraday Gap

Observed facts:

- last successful order pair before the no-trade complaint:
  - `12:17:38 KST` BUY, mock order id `0114708`
  - `12:18:11 KST` SELL, mock order id `0114869`
- `12:20` through `12:53`:
  - runtime continued to emit scanner/monitor artifacts
  - all executable decisions were NOOP
  - repeated reasons were `post_exit_cooldown`, `below_vwap_reclaim_not_ready`, `breakout_not_ready`, and `too_extended_from_vwap`
- `12:53:21` through `13:36:26`:
  - no canonical runtime runs were emitted
  - no active `run_session.py` / `run_m13_live_loop.py` process was found during inspection
  - no lock file was present before manual restart

Conclusion:

- `12:20-12:53` was strategy/monitor no-trade behavior.
- `12:53-13:36` was runtime inactivity and must be treated as an entrypoint/watchdog reliability issue.

## Why Current Behavior Is Too Conservative

The current frame often combines all of these at once:

- defensive playbook
- leader-only scanner bias
- VWAP reclaim required
- rebound required
- breakout confirmation expected
- volume confirmation expected
- post-exit cooldown
- memory bias that tightens entry/exit after recent losses

This can be reasonable during risk-off conditions, but it is too narrow as a default for neutral intraday operation.

The system is also not separating three different concepts cleanly enough:

1. No-trade because market quality is poor.
2. No-trade because the selected candidate is not ready.
3. No-trade because recent realized losses triggered conservative memory bias.

Those should produce different Commander actions.

## Cost And Exit Problem

The closed-trade reports show that many losses are small gross moves plus fee/tax drag.

Examples:

- `TRD_20260429_000660_02`
  - buy price `1,301,000`
  - sell price `1,301,000`
  - total cost `11,701`
  - net PnL `-11,701`
  - net PnL pct about `-0.90%`
- multiple `000660` trades show that high-priced one-share entries require a larger expected move just to break even.

This means entry and exit cannot be evaluated only by chart readiness. They also need a minimum expected move after broker cost.

## Required Improvements

### 1. Add Playbook Diversification

Strategist should not default to `defensive` on nearly every neutral-market run.

Required behavior:

- keep `defensive` for risk-off, weak breadth, poor liquidity, or degraded runtime states
- allow `breakout` or `momentum_pullback` when:
  - market regime is `neutral` or better
  - theme strength is available and positive
  - top candidate has sufficient trading value and volume quality
  - recent losses are cost/exit-driven rather than entry-signal failure

Validation target:

- In a neutral market session, `defensive` should not exceed 80% of fresh strategist frames unless Commander records an explicit reason.

### 2. Split Strict And Probe Entry Lanes

Monitor should keep the strict lane, but Commander should allow a bounded probe lane when repeated expandable blockers occur.

Strict lane:

- require VWAP reclaim
- require rebound
- require normal breakout or pullback confirmation
- normal position size

Probe lane:

- allow half-size or minimum-size entries only
- require at least:
  - `volume_ok=true`
  - `extension_ok=true`
  - candidate rank within Commander-expanded priority range
  - cost-adjusted expected move positive
- allow near-ready VWAP reclaim only when distance is inside a bounded tolerance
- never activate during open-position management, closeout, runtime degraded state, or post-exit hard cooldown

This is a participation lane, not a forced BUY.

### 3. Add Cost-Aware Entry Filter

Before accepting a BUY, Monitor/Decision should compare expected move to broker cost drag.

Required artifact fields:

- `cost_drag_pct`
- `breakeven_move_pct`
- `expected_move_pct`
- `cost_adjusted_edge_pct`
- `cost_filter_passed`
- `cost_filter_reason`

Initial rule:

- block new entries when `expected_move_pct < breakeven_move_pct + safety_margin_pct`
- apply stricter handling to high-priced one-share symbols where tax/fee drag dominates likely intraday movement

### 4. Loosen Exit Only After Cost Filter Exists

Exit sensitivity should not be relaxed blindly.

Required change order:

1. add cost-aware entry filter
2. record exit trigger quality and post-exit shadow movement
3. then consider loosening:
   - `peak_drawdown_exit_pct`
   - `intraday_low_break_pct`
   - confirmation ticks
   - minimum hold seconds

Reason:

- current exits are loss-heavy, but widening exits without improving entries can simply increase loss size.

### 5. Improve Runtime Watchdog

The `12:53-13:36` gap shows the official entrypoint can disappear without an immediate recovery path.

Required runtime-entrypoint improvement:

- watch process should detect missing lock owner and restart the official entrypoint
- watch status should emit `RED` when:
  - lock missing during market session
  - event lag exceeds threshold
  - no canonical run is emitted for more than two loop intervals
- restart attempts must write a structured event and log path

### 6. Fix Weekly Report Coverage

`2026-04-27` order events exist but PnL summaries were not included in the inspected closed-trade report aggregation.

Required trade-report/Kiwoom truth improvement:

- weekly profitability aggregation must reconcile:
  - order event log
  - `reports/trades/<day>`
  - Kiwoom day-trade truth (`ka10077`)
- missing PnL-report coverage must be surfaced as a data-quality warning, not silently treated as zero trades.

## Cross-Folder Ownership

| Area | Ownership |
| --- | --- |
| `docs/strategist_output` | playbook diversification, structured reason for defensive mode, scanner bias diversity |
| `docs/commander_control` | strict/probe lane authority, entry participation expansion, no forced BUY invariant |
| `docs/runtime_memory` | prevent recent loss memory from only tightening forever; distinguish cost/exit failure from entry-signal failure |
| `docs/strategy_horizon_feedback` | post-exit shadow data before loosening holds/exits |
| `docs/trade_report_plan` | weekly report coverage warnings and cost-aware report fields |
| `docs/kiwoom_truth` | broker truth and cost basis for PnL, fees, taxes, breakeven move |
| `docs/runtime_entrypoint` | watchdog, lock owner recovery, session gap visibility |

## Next Implementation Order

1. Add a weekly diagnostics script/report that emits:
   - order success counts
   - closed-trade PnL coverage
   - monitor blocker distribution
   - strategist playbook distribution
   - runtime gap intervals
2. Add cost-aware entry fields to monitor/decision/report surfaces.
3. Add strategist playbook diversification rules and validation.
4. Add Commander probe-lane policy for repeated expandable blockers.
5. Add watchdog restart policy for missing lock/event gaps.
6. Use post-exit shadow tracking before changing exit looseness.

## Validation Gates

Before enabling broader live behavior:

- cost-aware entry filter must be visible in canonical monitor and trade reports
- strategist fresh artifacts must show playbook selection reason and why defensive was or was not chosen
- Commander must show whether entry lane was `strict`, `probe`, or `blocked`
- Monitor must show whether it rejected for candidate quality, cost edge, or runtime/position guard
- runtime watch must detect and report lock/event gaps in the same day
