# Post-Q15 Close Decision - 2026-07-16

## Decision

`ADJUST_AND_RETEST`

The post-Q15 window is operationally closed under the precommitted Thursday-close
decision tree. The generic validation runner still prints `IN_PROGRESS (4/5)`
because its default gate is fixed at five trading days; that status does not
override this window-specific decision.

Q13/Q14 remain frozen. Q15 Candidate Filtering remains active. Exactly one Q15
condition is adjusted and no other trading behavior is changed.

## Evidence Window

- Days: 2026-07-13 through 2026-07-16
- Completed report days: 4 / 4
- Eligible trades: 11
- Result: 1 win / 10 losses
- Average return: -0.2798%
- Profit factor: 0.7238
- Maximum drawdown: -11.1436%
- Missing Evidence: 0%

Q13/Q14 root-cause totals:

| Root Cause | Count |
| --- | ---: |
| Scanner Ranking Failure | 5 |
| Strategist Override | 5 |
| Candidate Filtering | 0 |
| Exit Horizon | 6 |
| Missing Evidence | 0 |

The evidence does not support a broad Monitor relaxation or a broad Q15
rollback. It does support removing one false-positive pre-veto from Q15.

## Q15 Shadow Result

| Q15 Block Group | Count | +15m Avg Net | +30m Avg Net | Decision |
| --- | ---: | ---: | ---: | --- |
| `cost_edge_not_met` | 232 | -0.1357% | -0.2132% | retain |
| `rank_above_cascade_limit` | 201 | -0.3009% | -0.0827% | retain |
| `q15_score_gap` | 12 | +0.3371% | -0.1705% | retain; mixed |
| `q15_expected_blocker` | 178 | -0.0312% | +0.1064% | decompose |

Expected-blocker decomposition identified one repeat false-positive candidate:

| Expected Blocker | Count | +5m Avg Net | +15m Avg Net | +30m Avg Net |
| --- | ---: | ---: | ---: | ---: |
| `volume_insufficient` | 9 | +0.5845% | +0.7575% | +0.9607% |
| `below_vwap_reclaim_not_ready` | 161 | - | -0.0370% | +0.1030% |

`volume_insufficient` was positive across practical horizons and multiple days.
The other blocker groups are mixed or negative and are not changed.

## Applied Adjustment

Removed only `volume_insufficient` from the Q15 anticipated high-risk runner-up
blocker set.

This means:

- Q15 no longer rejects a runner-up solely because the candidate payload predicts
  `volume_insufficient` before Monitor evaluation.
- The candidate may reach Monitor for a current-data decision.
- Monitor's actual volume hard gate remains active.
- Cost floor, rank cap, score-gap, VWAP readiness, pullback maturity, strategist,
  commander, scanner ranking, entry, exit, and execution behavior are unchanged.

This is not a general volume-rule relaxation.

## Artifact Integrity Fixes

The close review found and fixed three reporting defects:

1. Per-order-pair Kiwoom truth now has precedence over symbol-day aggregate PnL
   during report regeneration.
2. Lifecycle bundles expose the authoritative exit execution details at the
   canonical top-level truth surface.
3. Repeated trades in the same symbol receive independent post-exit tracking.
   Fresh minute data is fetched once per symbol and reused for every trade.

2026-07-16 verification:

- Four 001790 round trips preserved their individual returns:
  `-0.09%`, `-1.08%`, `-0.93%`, `-1.41%`.
- Daily average return: `-0.8768%`.
- Post-exit recap: 4 / 4 observed and 4 / 4 EOD observed.
- Trade artifact health: 4 trade directories, 0 issues.

## Retest Contract

Observe exactly two full trading days with the adjusted Q15 rule.

During this retest:

- Q13/Q14 axes and formulas remain frozen.
- No additional behavior patch is allowed.
- Only observability, schema, artifact, and report-generation defects may be fixed.
- Compare `volume_insufficient` candidates reaching Monitor against the prior
  shadow cohort using the same +5m/+15m/+30m outcomes and realized results.

After two full days:

- `RETAIN`: actual Monitor rejections remain correct or admitted candidates improve
  opportunity capture without material loss regression.
- `ROLL_BACK`: admitted candidates are repeatedly loss-making after cost.
- `INSUFFICIENT_EVIDENCE`: no candidate reaches the affected branch; do not change
  another rule and report the absence explicitly.

## Deferred Candidate

The long-range June-to-July review still identifies `Scanner Ranking Failure` as
the largest behavior candidate. It is deferred until this two-day Q15 retest is
closed. No scanner score or ranking change is included in this patch.
