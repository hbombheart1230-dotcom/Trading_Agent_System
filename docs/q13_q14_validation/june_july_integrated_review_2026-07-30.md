# June-July Integrated Trading System Review - 2026-07-30

## Scope

- Confirmed performance cutoff: 2026-06-01 through 2026-07-29
- Current-session observation: 2026-07-30 through 13:02 KST
- Evaluation layers: Q8 through Q17
- Primary live-deployment cost assumption: 0.28% including slippage
- Mock-observed total drag: 1.086849%
- Behavior changes are not inferred from repeated runtime windows.

The 2026-07-30 session is not included in confirmed forward-performance
statistics because the session and EOD windows are incomplete.

## Executive Decision

The system should not be relaxed merely to produce trades.

The June-July evidence says:

1. Historical realized trading was materially loss-making.
2. Scanner Rank 1 was relatively better than lower ranks at 5m and 15m, but
   still had negative expectancy after estimated live cost.
3. The Strategist did not demonstrate ranking alpha over the same Scanner
   universe.
4. Q10, Q11, and Q12 controls did not reveal a profitable simple replacement.
5. Current cost, structure, volume, and pullback guards are preventing many
   trades, but recently rejected cost-edge candidates were also negative after
   live cost.
6. The only positive alpha-research candidate is the confirmed
   post-reclaim-pullback subtype. It is not yet an official policy.
7. The strongest authorized damage-reduction rule is the same-day,
   same-symbol reentry block after a realized loss.

The correct operating posture is low frequency and high selectivity. There is
no requirement to trade every day or every week.

## Realized Trading Performance

Daily scorecards contain 97 finite realized-return samples.

| Period | Trades | Wins | Losses | Flat | Win Rate | Avg Return | Profit Factor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| June | 56 | 5 | 50 | 1 | 8.93% | -1.1293% | 0.1822 |
| July through 7/29 | 41 | 5 | 36 | 0 | 12.20% | -0.7277% | 0.3047 |
| Combined | 97 | 10 | 86 | 1 | 10.31% | -0.9595% | 0.2259 |

July improved relative to June, but it did not become profitable. The result
does not support restoring the earlier high-frequency behavior.

The trusted same-symbol grouping contains 99 entries:

- first entries: 72
- same-day/same-symbol repeat entries: 27

The two-count difference from daily scorecards is a read-model coverage
difference: two ledger entries do not have finite scorecard return samples.
These populations must not be silently merged.

## Scanner Candidate Edge

The cumulative Scanner review contains:

- raw candidate rows: 61,644
- 15-minute independent episodes: 13,800
- compression ratio: 22.39%

Repeated 30-second decisions are not treated as independent opportunities.

Live-cost-adjusted episode expectancy:

| Rank | +5m | +15m | +30m |
| --- | ---: | ---: | ---: |
| Rank 1 | -0.2169% | -0.2265% | -0.3749% |
| Rank 2-3 | -0.3618% | -0.3878% | -0.2934% |
| Rank 4+ | -0.3718% | -0.4162% | -0.3119% |

Rank 1 is not a profitable policy by itself. Lower-ranked substitution also
does not solve the problem. The primary historical weakness is absolute
candidate edge after cost, not only which rank was selected.

Scanner score-component coverage is only 18.44% and spans two observed days.
That is enough to retain decomposition telemetry, but not enough to change
Scanner weights.

## Strategist Contribution

Paired daily Strategist B minus Scanner A return:

| Horizon | Observed Days | Better Days | Worse Days | Average Delta |
| --- | ---: | ---: | ---: | ---: |
| +5m | 25 | 12 | 12 | -0.0019% |
| +15m | 25 | 12 | 12 | -0.0594% |
| +30m | 25 | 12 | 12 | -0.0316% |
| EOD | 21 | 9 | 12 | -0.2645% |

The Strategist has not demonstrated measurable ranking alpha. This does not
justify removing the Strategist: its scenario, horizon, risk, and explanation
roles remain separate from candidate sourcing. It does mean its ranking
influence must not be assumed to add value.

Commander rejection often appears better because a rejection receives a cash
return of zero. That is defensive value, not proof of positive selection alpha.

## Independent Controls

Cost-adjusted cumulative results:

| Control | Sample | +5m | +15m | +30m | EOD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q10 Samsung/Hynix | 431 entries / 15 days | -1.1660% | -1.1518% | -1.0914% | -0.8669% |
| Q11 Opening Probe v0 | 66 trades / 26 days | n/a | n/a | -1.3618% policy result | n/a |
| Q12 BTC/Woori | 177 entries / 23 days | -1.2379% | -1.2846% | -1.3606% | -1.4947% |

The no-trade periods cannot be interpreted as obvious missed profit: all three
independent controls were negative.

## Q8-Q17 Final Status

| Phase | Status | Retained Conclusion |
| --- | --- | --- |
| Q8 | CLOSED | Broad VWAP, pullback, opening-momentum, runner-up relaxation rejected |
| Q9 | DIAGNOSIS COMPLETE | Candidate edge is cost-negative; orchestration alone is not the full cause |
| Q10 | CONTROL RETAINED | Samsung/Hynix simple baseline is not profitable |
| Q11 | CONTROL RETAINED | Opening probe v0 is not profitable |
| Q12 | CONTROL RETAINED | BTC/Woori baseline is not profitable |
| Q13 | FROZEN | Attribution axes retained; no new scoring axis |
| Q14 | FROZEN | Root-cause labels remain diagnostic; outcome-conditioned labels are not causal proof |
| Q15 | RETAIN | Automatic lower-rank cascade remains restricted |
| Q16 | RETAIN | ATR/volatility cannot substitute for directional edge |
| Q17 | CONTRACT REPAIRED | Memory path and horizon-matched evidence corrected |

Q18 is reserved for the bounded promotion review of the confirmed
post-reclaim-pullback subtype. It is not a new attribution or evaluation axis.
The post-cleanup canonical plan in
`q18_post_reclaim_promotion_review_plan_2026-07-30.md` supersedes the earlier
wording that no Q18 was required.

## Evidence-Backed Behavior Changes

### Same-Symbol Loss Reentry

| Cohort | Count | Win Rate | Avg Return | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| First entry | 72 | 13.89% | -0.8506% | 0.3072 |
| Repeat entry | 27 | 3.70% | -1.2478% | 0.0026 |
| Repeat after loss | 24 | 4.17% | -1.2756% | 0.0029 |

The same symbol is now blocked for the rest of the Korean trading day after a
full realized loss exit. Other symbols, partial exits, profitable exits, and
unknown-PnL exits are unaffected.

### Q16 Directional Evidence

Through 2026-07-29:

- exact proxy-only rejections: 132
- observed +30m outcomes: 128
- observed days: 5
- positive days: 1
- live-net +30m expectancy: -0.2478%
- live-net +30m profit factor: 0.6554

Retaining the proxy rejection rule is evidence-backed.

## Positive Research Candidate

Confirmed post-reclaim-pullback subtype:

| Horizon | Observations | Gross Expectancy | Live-Net Expectancy |
| --- | ---: | ---: | ---: |
| +5m | 25 | +0.3214% | +0.0414% |
| +15m | 25 | +0.4775% | +0.1975% |
| +30m | 25 | +0.5387% | +0.2587% |
| +60m | 25 | +0.5463% | +0.2663% |

Coverage is 100% across 13 observed days. This is the only current alpha
research candidate with positive live-cost expectancy.

It remains shadow-only because:

- the sample is small
- rows may be serially correlated
- profit factor and drawdown require episode-level confirmation
- it is negative under the unusually high mock-observed cost
- it has not been connected to Q17 runtime directional evidence

## Horizon Status

Operational holding limits:

| Strategy Horizon | Maximum Holding Contract | Directional Evidence |
| --- | --- | --- |
| scalp | 15 minutes | +5m |
| intraday | 4 hours | +30m |
| overnight_probe | next session / 1 day | next session open |
| 1_2day_swing | 2 days | +1 trading day |

The 5m and 30m values are evidence checkpoints, not forced exit times.

The contract is verified by code, deterministic replay, runtime artifact, and
tests. Corrected behavioral effectiveness cannot be proven without a naturally
occurring entry and exit.

Historical pre-repair horizon reports contain:

- June: 60 observed exits, 19 violation candidates, 10 cases where target hold
  would have improved the exit
- July: 44 observed exits, 17 violation candidates, 0 confirmed target-hold
  improvements

These rows justify the contract repair but must not be used to claim the
repaired policy is already profitable.

Horizon validation is event-driven, not calendar-driven:

1. On the next natural trade, verify persisted strategy horizon.
2. Verify the position keeps the same horizon context until full close.
3. Verify exit timing and reason against the horizon contract.
4. Compare actual exit with +5m/+15m/+30m/next-open/+1d counterfactuals where
   applicable.
5. Do not create a trade merely to test horizon behavior.

## Current Week Interpretation

Completed days 2026-07-27 through 2026-07-29 had no trades but valid Q9 evidence.

| Day | Q9 Windows | Commander Approve → Monitor NOOP | Rejected +30m Live-Net |
| --- | ---: | ---: | ---: |
| 7/27 | 485 | 205 | -0.2015% |
| 7/28 | 643 | 126 | -0.2163% |
| 7/29 | 525 | 315 | -0.2478% |

On 2026-07-30 through 13:02:

- Q9 evaluated candidates: 385
- triggered entry shapes: 23
- would-enter: 0
- all evaluated candidates failed cost edge
- dominant structure failures: below-VWAP reclaim, volume confirmation, and
  immature pullback
- Q10, Q11, and Q12 also produced no entry

This is a mixture of defensive success and strict filtering. Completed forward
outcomes, not trade count, determine whether the filtering was correct.

## Data Integrity Boundaries

Different read models answer different questions and have different counts:

- daily scorecard finite returns: 97
- trusted same-symbol grouping: 99
- Q13 attribution read model through 7/27: 107
- Q14 root-cause range through 7/16: 104

These counts must not be presented as one interchangeable trade population.
Older June artifacts have missing pre-Strategist and raw Scanner evidence.
Q13 therefore records many rows as `MISSING` or `INSUFFICIENT_EVIDENCE`.

Confirmed strengths:

- selection integrity average: 95.15
- evidence quality average: 93.29

Diagnostic weaknesses:

- scanner alignment average: 72.07
- exit horizon average: 77.70
- entry timing has only 9 scored days and is not established as the primary
  failure

Scanner alignment is an attribution axis, not automatic proof that Scanner
weights should change.

## Next Decision Sequence

1. Finish 2026-07-30 EOD forward observations and regenerate the daily bundle.
2. Determine whether today's 23 triggered-but-blocked shapes were positive
   after 5m, 15m, 30m, and live cost.
3. Keep the Q15/Q16 guards and same-symbol loss reentry control unchanged.
4. Validate Q17 horizon behavior on the next natural completed trade.
5. Continue collecting score-component decomposition without changing ranking
   weights until coverage spans more than the current two days.
6. Perform an episode-level promotion review for the confirmed post-reclaim
   subtype, including profit factor, drawdown, day concentration, and market
   regime.
7. If that subtype remains positive, promote only that one bounded setup.
8. If it fails, retain the current low-frequency posture; do not compensate by
   broadly relaxing entry gates.

The next objective is not more evaluation architecture. It is one bounded
promotion decision based on the existing frozen evaluation system.
