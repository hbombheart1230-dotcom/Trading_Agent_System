# Opening Rank-1 Deep Dive

## Scope

This review explains the retrospective `OPEN_0_20_RANK1_30M` cohort.
It does not promote or modify trading behavior.

- Range: 2026-06-24 through 2026-07-30
- Population: opening 20-minute Scanner Rank-1 episodes
- Observed +30m cases: 65
- Entry: first one-minute candle strictly after the decision
- Exit: fixed +30-minute observation
- Cost: 0.28% round trip

Generated evidence:

- `reports/evaluation/offline_alpha/opening_rank1_deep_dive/opening_rank1_deep_dive.json`
- `reports/evaluation/offline_alpha/opening_rank1_deep_dive/opening_rank1_cases.csv`
- `reports/evaluation/offline_alpha/opening_rank1_deep_dive/opening_rank1_deep_dive.md`

## Data Coverage

| Evidence | Coverage |
|---|---:|
| Symbol name | 65/65 |
| Current Kiwoom theme reference | 42/65 |
| Original Q9 decision window | 65/65 |
| Point-in-time macro snapshot at or before decision | 51/65 |
| Strategist scenario | 64/65 |
| Tactical ID | 6/65 |
| Detailed score breakdown | 13/65 |
| Same-day actual trade | 7/65 |
| Actual trade overlapping the opening observation window | 3/65 |

The historical Q9 schema retained scenario and playbook broadly, but tactical IDs,
candidate sources, and detailed factor fields were sparse in older windows. Missing
fields remain missing instead of being inferred.

Theme names are current Kiwoom references. They are not point-in-time historical
membership and cannot be used as a causal explanation. Historical Q9 only proves
`theme_match` or `theme_boost` when those fields exist.

## Main Result

| Metric | Result |
|---|---:|
| Cases | 65 |
| Win rate | 61.54% |
| Average net +30m return | +0.7502% |
| Median net +30m return | +0.3546% |
| Profit factor | 1.7727 |
| Average MFE | +3.2351% |
| Average MAE | -2.2742% |
| Positive-day ratio | 62.50% |
| Median daily mean return | +0.2681% |

## Outlier Sensitivity

The average is materially affected by a few large winners.

| Test | Average net return |
|---|---:|
| All 65 | +0.7502% |
| Remove largest winner | +0.4657% |
| Remove top 3 winners | -0.0624% |
| Remove top 5 winners | -0.3036% |
| Remove top and bottom 3 | +0.3543% |
| Winsorize each result to +/-5% | +0.2554% |

The top three winners contributed +52.6348 percentage points and 47.05% of all
positive gains. This means the cohort has a positive median and positive-day ratio,
but its average-return edge depends on capturing rare opening expansions.

## Timing Structure

| Decision time | N | Win rate | Average net | Median net | PF |
|---|---:|---:|---:|---:|---:|
| 09:00-09:04 | 26 | 73.08% | +1.8602% | +1.4914% | 3.2370 |
| 09:05-09:09 | 7 | 14.29% | -2.4557% | -1.0117% | 0.1463 |
| 09:10-09:14 | 6 | 66.67% | -0.7891% | +0.2529% | 0.2946 |
| 09:15-09:19 | 26 | 61.54% | +0.8587% | +0.2606% | 2.5250 |

The signal is not a smooth 20-minute opening effect. The first five minutes were
strong, the next five were poor, and the last five contained both ordinary returns
and the single largest winner. Prospective validation must preserve these buckets.

## Market Context

Among the 51 cases with a point-in-time macro snapshot:

| Market bucket | N | Win rate | Average net | Median net | PF |
|---|---:|---:|---:|---:|---:|
| Sharp down | 18 | 66.67% | +1.6683% | +0.5600% | 8.1488 |
| Strong up | 17 | 64.71% | -0.3527% | +0.5871% | 0.6856 |
| Up or flat | 15 | 40.00% | +0.0783% | -0.7176% | 1.0496 |

The preliminary association is closer to opening relative-strength/reversal during
weak index conditions than to indiscriminate participation in a strong market.
This is descriptive only: the market groups are small and returns are skewed.

## Strategy And Scanner Evidence

- Strategist scenarios did not separate win rate strongly:
  - neutral: 61.76%, average +0.4761%
  - risk-off: 64.71%, average +1.2803%
  - risk-on: 61.54%, average +0.8745%
- Scanner score also had little separation:
  - winner mean 0.9286
  - loser mean 0.9056
  - standardized difference 0.07
- Confidence separation was also small, with standardized difference 0.15.
- Tactical IDs existed in only 6 cases. The four recorded
  `vwap_reclaim_pullback` cases averaged -0.4376%, but this is not enough evidence
  to judge that tactic.
- `sector_theme_only` cases were weak: 10 cases, 50% win rate, average -0.5136%,
  PF 0.5713.
- Source information was not retained for 51 cases. Those rows must not be
  re-labelled as market-native after the fact.

The observed edge is therefore not explained by a higher absolute Scanner score,
Strategist scenario, or one recorded tactical ID. Rank position plus exact opening
timing appears more important than the score magnitude.

## Price Path

- Negative +5m then positive +30m: 23 cases
- Positive +5m then negative +30m: 4 cases
- MAE below -1% followed by a +30m win: 15 cases
- MFE above +1% followed by a non-positive +30m result: 5 cases

The candidate often needed to survive opening noise before the 15-30 minute move.
That explains why the previously tested tight stop/target policies were negative.
It does not authorize a wider stop: average MAE was -2.27%, so risk is substantial.

## Actual Trade Cross-Check

Only three virtual cases overlap an actual opening-window trade:

| Day | Symbol | Virtual +30m | Actual result | Actual hold |
|---|---|---:|---:|---:|
| 2026-07-10 | 233740 KODEX KOSDAQ150 Leverage | +4.3849% | -0.5103% | 40 sec |
| 2026-07-15 | 005360 Monami | +9.9600% | +8.0662% | 556 sec |
| 2026-07-15 | 396500 TIGER Semiconductor TOP10 | +1.6235% | -0.8249% | 38 sec |

This tiny cross-check illustrates an implementation gap: two positive 30-minute
paths became actual losses after very short holds. It is not enough to prescribe a
new hold rule, but it supports validating horizon compliance separately from
candidate quality.

## Interpretation

The most defensible explanation is:

1. Cross-sectional Rank-1 during opening price discovery sometimes captured rare,
   large directional expansions.
2. The effect was concentrated in exact time buckets, especially 09:00-09:04.
3. Weak-index sessions may have improved the value of stock-level relative
   strength, while broad strong sessions did not guarantee positive expectancy.
4. The path frequently included an initial adverse move, so a short-horizon exit
   could erase the candidate-selection advantage.
5. The aggregate average is fragile to the top three winners. The result is a
   bounded prospective hypothesis, not an established production edge.

The frozen prospective validator remains the correct next step. It must determine
whether the positive median, positive-day ratio, and exact time-bucket structure
repeat without retrospective selection.

## Second-Pass Price Arc Decomposition

The aggregate was decomposed by the price path relative to the previous close.
These labels use future 30-minute highs and are diagnostic labels, not entry
conditions.

| Price arc | N | Win rate | Average net | Median net | PF |
|---|---:|---:|---:|---:|---:|
| Normal | 49 | 61.22% | -0.0130% | +0.3420% | 0.9850 |
| Gap or momentum | 9 | 44.44% | -1.2150% | -0.5560% | 0.3210 |
| Limit-up trajectory | 5 | 80.00% | +7.8670% | +9.9600% | 9.0500 |
| Crash reversal | 2 | 100.00% | +10.4930% | +10.4930% | not meaningful |

The normal 49-case population had no net expectancy after cost. The historical
aggregate edge came almost entirely from five limit-up trajectories and two
same-symbol crash-reversal observations.

The largest cases were two different mechanisms:

1. Opening momentum toward the daily upper limit:
   - 005360 Monami on July 10 and July 15
   - 011230 Samhwa Electronics on July 23
2. Opening dislocation reversal:
   - 009730 Irem on July 20, entered near -16% versus the previous close

The crash-reversal result is one symbol on one day and is not a promotable
hypothesis.

## Pre-Decision Screens

The following conditions use only information available at the decision. They were
defined after inspecting the cohort and therefore require untouched prospective
validation.

| Screen | N | Days | Win rate | Average | Median | PF | Average without top 3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 09:00-09:04 | 26 | 20 | 73.08% | +1.8602% | +1.4914% | 3.237 | +0.2057% |
| 09:01-09:04, completed-bar relative volume >=1x, entry <+20% vs prior close | 5 | 5 | 80.00% | +1.4393% | +1.9612% | 13.948 | +0.5338% |
| 09:01-09:04, completed-bar relative volume >=2x, entry <+20% vs prior close | 4 | 4 | 75.00% | +1.3088% | +1.8250% | 10.419 | -0.5558% |
| 09:15-09:19, less than +7% from opening price | 25 | 15 | 64.00% | +1.1123% | +0.3052% | 4.037 | +0.0418% |
| Prior Rank-1 observation and no chase | 13 | 12 | 84.62% | +2.2122% | +0.7563% | 6.943 | +0.1872% |

Only the exact 09:00-09:04 time screen and the late no-chase screen have enough
breadth to be prospectively screenable. The late screen is fragile because its
average excluding the top three is only +0.0418%.

The initial second-pass calculation incorrectly included unfinished minute-bar
volume in decisions made during the first minute. That was look-ahead information.
After restricting volume to bars fully completed before the decision, the early
relative-volume screens fell to five and four observations. They are not evidence.

Rank-1 was not always the highest `score_total` candidate. In 24 of 65 cases the
Rank-1 candidate had a lower score total than another row, reflecting confidence,
risk, and ranking adjustments. The effect must therefore be described as
pre-Strategist intrinsic Rank-1 behavior rather than highest raw Scanner score or
final post-Strategist Rank-1 behavior.

No runtime behavior should be changed from this second-pass review. The appropriate
next artifact is a frozen prospective comparison with:

- exact 09:00-09:04 screen,
- completed-bar opening relative volume, with first-minute decisions explicitly
  marked unavailable,
- entry distance from previous close,
- fillability and spread evidence,
- separate limit-up-trajectory and normal-return reporting.

## Fixed Interpretation

This review does not establish a universal `Rank-1 + 30m` rule.

### Retain for prospective testing

1. **Primary time window: 09:00-09:04**
   - 26 cases across 20 days.
   - Average +1.8602%, median +1.4914%, PF 3.2370.
   - Average remained +0.2057% after removing the top three observations.
   - Removing all limit-up and crash-reversal diagnostics left 22 cases,
     average +0.1229%, median +0.8854%, and PF 1.1250.
   - The residual is positive but thin. The rare expansion cases still explain
     most of the economically meaningful result.
2. **No-chase evidence**
   - Entries at least +7% above the opening price had four cases, 25% win rate,
     average -3.3608%, and PF 0.0418.
   - This is a risk flag for prospective reporting, not yet a hard gate.
3. **VWAP state**
   - Above VWAP: 12 cases, 75% win rate, average +0.9229%, PF 8.6444.
   - Below VWAP: 9 cases, 33.33% win rate, average -1.0384%, PF 0.301.
   - Coverage is only 21 of 65, so VWAP is supporting evidence only.

### Do not promote

- **Normal Rank-1 path:** 49 cases averaged -0.0127% after cost, PF 0.9852.
  There is no broad post-cost edge.
- **Crash reversal:** two observations were the same symbol on the same day.
  This is one event, not a repeatable pattern.
- **Relative volume alone:** its buckets were not monotonic.
- **Scanner score threshold:** winner and loser score separation was negligible.
- **Future Rank persistence:** this is look-ahead information.
- **Current theme membership or news attribution:** historical direct catalyst
  evidence was incomplete and some news mappings were noisy. No causal claim is
  justified.

### Diagnostic interpretation of the rare winners

The exceptional observations came from two different mechanisms and must not be
combined into one tactic:

1. **Opening expansion toward the upper limit**
   - Monami on July 10 and July 15.
   - Samhwa Electronics on July 23.
   - The shared observable candidates were very early decision time, strong
     relative activity, and a price that had not already advanced more than
     roughly 20% versus the previous close at the reference entry.
2. **Deep opening dislocation reversal**
   - Irem on July 20 near -16% versus the previous close.
   - Both observations came from the same event, so this mechanism is rejected
     until independently repeated.

Two other upper-limit trajectories entered after approximately +25% versus the
previous close and produced weak or negative results. Being near the upper limit is
not itself an entry condition; fillability, remaining price room, spread, and the
time at which the move was recognized must be retained prospectively.

## Prospective Evidence Contract

The broad opening Rank-1 cohort remains frozen so that it provides a control group.
Reports should compare the following additive subgroups without changing orders:

| Subgroup | Definition | Role |
|---|---|---|
| Broad control | Rank-1 at 09:00-09:19 | Detect whether the original effect repeats |
| Exact opening | Rank-1 at 09:00-09:04 | Primary timing hypothesis |
| Completed-volume screen | 09:01-09:04 + completed-bar relative volume >=1x + entry <+20% vs prior close | Sparse secondary observation |
| Opening chase | Entry >=+7% versus opening price | Risk comparison |
| Above VWAP | Point-in-time price above VWAP | Supporting condition |
| Late no-chase | 09:15-09:19 and entry <+7% versus opening | Secondary, fragile screen |

For each subgroup retain:

- decision timestamp to the second,
- reference-entry delay,
- prior close, opening price, and reference-entry price,
- point-in-time cumulative volume and historical same-clock volume reference,
- VWAP state and distance,
- Rank-1/Rank-2 score, confidence, and risk deltas,
- best bid, best ask, spread, upper-limit price, and remaining room when available,
- +1m, +3m, +5m, +15m, +30m, +60m, and EOD returns,
- MFE, MAE, and time to each,
- day and symbol concentration,
- missing evidence reasons.

The result is promotion-eligible only if it repeats prospectively without relying
on the five historical limit-up cases. Until then, this remains observation only.

## Downstream Fate Of The Three First-Minute Expansions

The three strongest first-minute expansion cases shared Scanner intrinsic Rank-1,
but downstream handling differed.

| Case | Scanner intrinsic | Strategist result | Monitor candidate / Commander approval | Observed result |
|---|---|---|---|---|
| 2026-07-10 Monami | Rank-1 | Monami remained Rank-1 | Monitor candidate 069540 (Rank-5); Commander approved | Executed +0.473%; Monami virtual +16.340% |
| 2026-07-15 Monami | Rank-1 | Monami remained Rank-1 | Monitor candidate Monami; Commander approved | Actual +8.066%; virtual +9.960% |
| 2026-07-23 Samhwa Electronics | Rank-1 | Samhwa moved to Rank-3; 000227 became Rank-1 | Monitor NOOP; Commander rejected 000227 for risk | Samhwa virtual +17.336% |

This is not enough to conclude that Strategist, Monitor, or Commander generally
destroys alpha. Commander remained an approval/veto authority; the changed symbol
on July 10 was the candidate presented by the Monitor, not an autonomous Commander
selection. The comparison does show that the common detector in all three rare
cases was the Scanner intrinsic ranking, while the downstream chain preserved and
executed only one of them. Future comparison must therefore retain the candidate at
every stage instead of treating all Rank-1 labels as the same authority.

## Strategy Common-Denominator Check

All three first-minute upper-limit expansions were associated with the `breakout`
playbook, but the playbook is not independently profitable:

| Breakout population | N | Average net | Median net | PF |
|---|---:|---:|---:|---:|
| All breakout observations | 11 | +3.5048% | +1.6235% | 3.7677 |
| Excluding limit-up trajectories | 6 | -0.1305% | +0.9644% | 0.9134 |
| Breakout outside 09:00-09:04 | 5 | -1.4291% | +0.3052% | 0.4248 |
| 09:00-09:04 breakout excluding rare trajectories | 3 | +0.6876% | +1.6235% | 2.3688 |

The useful hypothesis is therefore not `breakout` alone. It is the interaction
between **pre-Strategist intrinsic Rank-1, the first five minutes, breakout framing,
and immediate continuation**. The non-rare residual has only three cases and must
remain observational.

## What Actually Identified The Exceptional Opening Surges

The three strong upper-limit trajectories that were identified in the first minute
were:

| Day / time | Symbol | Entry vs prior close | Entry vs open | Scanner score | Confidence | +1m after reference entry | +30m net |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-07-10 09:00:06 | 005360 Monami | +3.98% | +0.57% | 1.608 | 0.918 | +8.23% | +16.34% |
| 2026-07-15 09:00:14 | 005360 Monami | +17.92% | 0.00% | 1.647 | 0.966 | +5.76% | +9.96% |
| 2026-07-23 09:00:13 | 011230 Samhwa Electronics | +8.29% | +2.93% | 0.767 | 0.861 | +9.79% | +17.34% |

What is known:

- Scanner had already assigned final Rank-1 within the first 6-14 seconds.
- The reference entry had not chased more than +3% from the opening price.
- All three immediately expanded during the minute after the reference entry.
- Two Monami cases had high scores and wide Rank-1 gaps, but Samhwa Electronics
  did not. Absolute score and Rank gap are not common necessary conditions.

What is not known:

- No completed one-minute volume existed at the decision time.
- Point-in-time VWAP evidence was missing.
- Point-in-time direct catalyst evidence was missing or too noisy.
- Market-index evidence was missing for two of the three cases and flat for one.

Therefore, the retained explanation is **very-early cross-sectional recognition
plus immediate continuation**, not a proven volume, news, theme, or market-regime
rule. To determine why Scanner recognized the move in the first seconds, future
observation must retain tick-level price velocity, auction gap, turnover
acceleration, best bid/ask and spread, ask-side depth, upper-limit distance, and
the exact source scores available at the decision. These are observability fields,
not entry rules.

## Market-Condition Finding

Market regime did not explain the exact-opening result reliably:

| Exact 09:00-09:04 market evidence | N | Win rate | Average net |
|---|---:|---:|---:|
| Missing | 14 | 78.57% | +1.9555% |
| Strong up | 3 | 66.67% | +0.6918% |
| Up or flat | 6 | 50.00% | +2.1309% |
| Sharp down | 3 | 100.00% | +2.0429% |

Fourteen of 26 exact-opening cases lacked point-in-time macro evidence, and each
observed market bucket was too small. The broad sample's sharp-down association
may describe relative-strength or reversal behavior, but it is not a usable
market-regime condition. Future evidence should retain KOSPI/KOSDAQ moves, KRX
night futures, US semiconductor context, and market breadth at the exact decision
without making any of them a gate.
