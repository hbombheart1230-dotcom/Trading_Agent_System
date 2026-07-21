# Post-Q15 Two-Day Decision Tree - 2026-07-14

## Purpose

This document fixes the decision tree for the next two trading days after the
Q15 `Candidate Filtering` patch.

The goal is not to add another evaluation axis. The goal is to decide, after
two more full trading days, whether Q15 is helping, harming, or simply exposing
the next root cause.

Q13/Q14 remain frozen.

No new scanner, strategist, commander, monitor, entry, exit, or execution logic
may be changed during this window unless an observability bug prevents evidence
collection.

## Current Phase

Current phase:

```text
Q13/Q14 frozen attribution system
-> Q15 Candidate Filtering applied after 2026-07-10 close
-> Post-Q15 validation
-> Two more trading days
-> Thursday close decision
```

A `NO_GO` result during this phase does not automatically roll back Q15.

It means:

- do not apply another behavior patch yet
- first determine whether Q15 caused opportunity loss, reduced bad runner-up
  leakage, or exposed a different root cause

## Required Evidence After Each Day

Collect and compare these reports:

- `reports/evaluation/daily/YYYY-MM-DD/no_trade_attribution_report.md`
- `reports/evaluation/daily/YYYY-MM-DD/scanner_alignment_root_cause_report.md`
- `reports/evaluation/daily/YYYY-MM-DD/attribution_score_v0.md`
- `reports/operator_summary/daily/YYYY-MM-DD/q8_shadow_blocker_review.md`
- `reports/operator_summary/daily/YYYY-MM-DD/daily_summary.md`
- Q10 Samsung/Hynix baseline comparison
- Q11 opening opportunity shadow report
- Q12 BTC/Woori baseline report

Minimum fields to check:

- actual trade count
- no-trade count
- Commander approve count
- Monitor `NOOP` count
- blocked candidate count
- Q15 skipped runner-up count
- blocked candidate forward returns after cost
- scanner rank 1 forward returns after cost
- Q10/Q11/Q12 baseline forward returns
- Missing Evidence ratio

## Decision Case A - Q15 Killed Good Runner-Up Opportunities

### Definition

Q15 is harming opportunity capture if candidates blocked specifically by Q15
show repeated positive forward outcomes after cost.

Relevant blocker reasons:

- `q15_score_gap_above_runner_up_limit`
- `q15_runner_up_expected_blocker`
- `rank_above_cascade_limit` when caused by the Q15 rank cap

Evidence pattern:

- Q15-skipped runner-ups have positive average net return after cost on at
  least one practical horizon: `+15m`, `+30m`, or `EOD`
- Q15-skipped runner-ups outperform executed trades or scanner rank 1
- Q15-skipped runner-ups show repeat wins across both remaining days, not just
  one isolated symbol

### Example

| Group | Count | +30m Win Rate | +30m Avg Net |
|---|---:|---:|---:|
| Q15 skipped runner-ups | 40 | 55% | +0.35% |
| Scanner rank 1 | 30 | 20% | -0.80% |
| Actual trades | 5 | 20% | -0.60% |

### Action

Do not remove Q15 entirely first.

Review the specific Q15 condition that killed winners:

1. If score-gap blocks are the problem, relax `q15_max_score_gap`.
2. If blocker-gate blocks are the problem, remove only the one false-positive
   blocker from the high-risk blocker list.
3. If rank cap blocks are the problem, raise the rank cap by one step only.

Patch rule:

- one adjustment only
- preserve Q13/Q14 evaluation
- compare before/after using the same blocked-runner-up table

## Decision Case B - Monitor Hard Gates Are Too Strict

### Definition

Monitor is over-filtering if Commander approves candidates but Monitor converts
them to `NOOP`, and those blocked candidates later show repeated positive
forward outcomes after cost.

Relevant blocker reasons:

- `cost_floor_not_met`
- `below_vwap_reclaim_not_ready`
- `pullback_not_mature`
- `breakout_not_ready`
- `volume_confirmation_missing`
- `volume_insufficient`

Evidence pattern:

- Commander approval count is high
- Monitor `NOOP` count is high
- blocked candidates outperform scanner rank 1, actual trades, or Q10/Q11/Q12
  baselines
- the same blocker reason repeatedly blocks later winners

### Example

| Block Reason | Count | +15m Win Rate | +15m Avg Net | EOD Avg Net |
|---|---:|---:|---:|---:|
| `below_vwap_reclaim_not_ready` | 120 | 48% | +0.22% | +0.70% |
| `pullback_not_mature` | 70 | 44% | +0.10% | +0.45% |
| `cost_floor_not_met` | 200 | 18% | -0.50% | -0.20% |

### Action

Patch only the repeated false-positive hard gate.

Examples:

- If `below_vwap_reclaim_not_ready` blocks winners, add a reclaim-in-progress
  exception only when volume and relative strength improve.
- If `pullback_not_mature` blocks winners, allow a small probe only when MFE
  history and market rail support it.
- If `volume_confirmation_missing` blocks winners, replace static volume
  thresholding with relative intraday volume context.

Do not loosen all Monitor gates.

## Decision Case C - Monitor Blocks Are Correct

### Definition

Monitor is not the problem if blocked candidates are also negative after cost.

Evidence pattern:

- blocked candidates have negative average net returns
- win rate is low across `+5m`, `+15m`, `+30m`, and `EOD`
- Q15-skipped runner-ups are also negative
- no-trade days preserve capital relative to candidate forward outcomes

### Example

| Group | Count | +30m Win Rate | +30m Avg Net |
|---|---:|---:|---:|
| Monitor blocked candidates | 300 | 3% | -2.00% |
| Q15 skipped runner-ups | 60 | 5% | -1.70% |
| Scanner rank 1 | 80 | 8% | -1.40% |

### Action

Do not loosen Monitor.

Move the next investigation to scanner candidate quality:

1. scanner rank 1 forward returns
2. raw scanner score component decomposition
3. theme/sector source contribution
4. market-regime fit
5. whether fixed baselines, such as Samsung/Hynix, outperform the scanner
   universe

Likely next behavior candidate:

- `Scanner Ranking Failure`

## Decision Case D - Scanner Rank 1 Is Also Weak

### Definition

The system has a scanner-quality problem if rank 1 itself performs poorly even
when it is selected directly.

Evidence pattern:

- selected symbol equals raw scanner rank 1
- realized or forward return is repeatedly negative
- blocked runner-ups are not materially better
- Q10 or other fixed baselines outperform scanner rank 1

### Example

| Group | Count | +30m Avg Net | EOD Avg Net |
|---|---:|---:|---:|
| Scanner rank 1 | 90 | -1.20% | -0.80% |
| Q15 blocked runner-ups | 50 | -1.50% | -1.00% |
| Samsung/Hynix baseline | 40 | -0.20% | +0.90% |

### Action

Do not patch Monitor.

Do not patch Strategist first.

Patch scanner scoring only after selecting one component defect.

Candidate component defects:

- VWAP reclaim not ready is ranked too high
- volume surge behaves like late-chase risk
- weak relative strength is under-penalized
- macro chart fit is overweighted for short-horizon trades

Patch rule:

- one score component only
- no full scanner rewrite
- Q13/Q14 continues unchanged for before/after comparison

## Decision Case E - Exit Horizon Remains The Dominant Problem

### Definition

Exit horizon is the next target only if entries are acceptable but post-entry
data shows repeated early exit or wrong hold horizon behavior.

Evidence pattern:

- entry forward MFE is positive
- realized return is negative or much worse than MFE
- post-exit shadow shows better prices after exit
- strategy horizon says intraday or longer but actual holding is seconds or a
  few minutes

### Example

| Exit Reason | Trades | Avg Hold | Avg MFE | Avg Return |
|---|---:|---:|---:|---:|
| `intraday_low_break` | 12 | 90 sec | +0.80% | -0.70% |
| `vwap_loss` | 8 | 3 min | +0.50% | -0.40% |

### Action

Patch only the repeated exit reason.

Examples:

- require two-bar confirmation for non-hard-stop exits
- align minimum hold time with strategist horizon
- make hard stop exceptions explicit

Do not delay all exits globally.

## Decision Case F - Evidence Is Still Insufficient

### Definition

The two-day window is inconclusive if artifacts are missing or the market
produces too few comparable candidates.

Evidence pattern:

- Missing Evidence exceeds threshold
- forward observations are not available
- Q9/Q10/Q11/Q12 artifacts are incomplete
- both days have near-zero candidate evidence

### Action

Do not patch behavior.

Fix only instrumentation or artifact completeness.

If instrumentation is clean but the market is quiet, extend observation by a
fixed two trading days. Do not extend indefinitely.

## Thursday Close Decision Template

Use this template after the second trading day completes.

### Summary

- Observation days:
- Actual trades:
- Q9 decision windows:
- Commander approvals:
- Monitor NOOP count:
- Q15 skipped runner-ups:
- Missing Evidence:

### Q15 Opportunity Cost

| Q15 Block Reason | Count | +15m Avg Net | +30m Avg Net | EOD Avg Net | Decision |
|---|---:|---:|---:|---:|---|

### Monitor Over-Filtering

| Monitor Block Reason | Count | +15m Avg Net | +30m Avg Net | EOD Avg Net | Decision |
|---|---:|---:|---:|---:|---|

### Scanner Rank 1 Quality

| Group | Count | +15m Avg Net | +30m Avg Net | EOD Avg Net |
|---|---:|---:|---:|---:|
| Scanner rank 1 |
| Q15 skipped runner-ups |
| Monitor blocked candidates |
| Samsung/Hynix baseline |
| Q11 opening opportunity |

### Final Case

Choose exactly one:

- Case A: Q15 killed good runner-up opportunities
- Case B: Monitor hard gates are too strict
- Case C: Monitor blocks are correct
- Case D: Scanner rank 1 is also weak
- Case E: Exit horizon is dominant
- Case F: Evidence is insufficient

### Next Action

Choose exactly one:

- keep Q15 unchanged
- adjust one Q15 runner-up gate
- adjust one Monitor hard gate
- patch one scanner score component
- patch one exit reason
- fix instrumentation only
- extend observation by exactly two trading days

## Non-Negotiable Rule

Do not apply multiple behavior changes at once.

The purpose of this decision tree is to prevent another cycle of broad,
ambiguous patches.
