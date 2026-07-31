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
