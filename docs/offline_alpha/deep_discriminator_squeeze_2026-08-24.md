# Deep Discriminator Squeeze Review (2026-08-24)

## Scope

- Existing artifacts only; no trading behavior change.
- Canonical Rank-1 feature mart: 129 episodes, 113 independent day-symbols, 2026-06-24 through 2026-08-24.
- Prospective opening shadow: 64 episodes across 13 days.
- Returns use the 0.28% real-account round-trip drag already fixed by the evaluation contract.
- Results are exploratory where a rule was discovered after looking at the same sample.

## Executive Conclusion

The accumulated data does contain discriminators. The strongest common structure is not `Rank-1`, `risk=HIGH`, or VWAP pullback by itself. It is:

> Early common-stock candidates with real directional components produce short-lived alpha, while liquidity-led ETF candidates and indiscriminate long holding destroy it.

The original prospective-risk review contained eight `risk=HIGH + common_stock`
observations: all eight were positive at +5m, seven were positive at +15m, and six
were positive at +30m. Expanding through the canonical opening history and then
deduplicating to the first day-symbol observation produces 16 historical discovery
rows. That expanded cohort remains positive but is not prospective evidence. The
edge decayed materially toward EOD.

This does not authorize a behavior patch because the rule was found post hoc and overlaps with `IMMEDIATE_OPENING_PROBE`, `scalp`, and `DIRECTIONAL_BREADTH`. It does justify one fixed prospective shadow specification.

## 1. Canonical Rank-1 Horizon Path

| Horizon | N | Win Rate | Avg Net | Median | Profit Factor |
| --- | ---: | ---: | ---: | ---: | ---: |
| +5m | 107 | 40.2% | +0.274% | -0.280% | 1.33 |
| +15m | 107 | 50.5% | +0.773% | +0.026% | 1.88 |
| +30m | 107 | 57.0% | +0.699% | +0.247% | 1.74 |
| +60m | 107 | 50.5% | +0.648% | +0.016% | 1.47 |
| +120m | 107 | 43.9% | +0.251% | -0.280% | 1.14 |
| +180m | 105 | 45.7% | -0.016% | -0.280% | 0.99 |
| EOD | 107 | 49.5% | -0.243% | -0.035% | 0.90 |

The broad Rank-1 path peaks around +15m to +30m and loses its edge by EOD. Broad Rank-1 buying remains rejected because the distribution is heterogeneous and contributor-dependent.

## 2. Immediate Opening Probe

| Horizon | N | Win Rate | Avg Net | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| +5m | 13 | 76.9% | +2.304% | 8.17 |
| +15m | 13 | 53.8% | +1.656% | 3.68 |
| +30m | 13 | 53.8% | +0.994% | 1.97 |
| +60m | 12 | 58.3% | +2.025% | 2.66 |
| EOD | 11 | 54.5% | -0.035% | 0.99 |

Removing the best observation leaves N=12, 75.0% wins, +1.321% average net, and PF 4.80 at +5m. The immediate-opening edge is not explained by one winner alone.

### Asset Interaction

| Asset | N | +5m Avg | +15m Avg | +30m Avg | EOD Avg |
| --- | ---: | ---: | ---: | ---: | ---: |
| Common stock | 6 | +4.901% | +3.742% | +1.970% | -6.557% |
| ETF | 7 | +0.078% | -0.132% | +0.158% | +5.401% |

All six immediate common-stock observations were positive at +5m. Common-stock alpha was front-loaded and suffered severe profit fade by EOD. ETF EOD performance is not generalizable because seven observations are dominated by `233740`.

## 3. Risk HIGH Is an Asset-Conditional Signal

| Asset Class | N | +30m Win Rate | Avg Net | Median | Profit Factor |
| --- | ---: | ---: | ---: | ---: | ---: |
| Common stock | 8 | 75.0% | +3.390% | +2.985% | 13.85 |
| Leveraged ETF | 7 | 42.9% | -0.426% | -0.901% | 0.68 |
| Inverse ETF | 2 | 0.0% | -1.389% | -1.389% | 0.00 |

For `HIGH + common_stock`, every single-symbol and single-day leave-one-out result remained positive:

- Win rate range: 66.7% to 85.7%.
- Average net range: +2.562% to +4.039%.
- Minimum observed PF: 8.28.

Within HIGH observations, common stocks beat non-common assets at both +5m and +30m. A one-sided exact contingency calculation gives approximately 0.68% for the +5m split and 4.45% for the +30m split. These are descriptive only because the subtype was discovered after multiple comparisons and observations are not guaranteed independent.

### Profit Fade Within HIGH Common Stocks

| Horizon | N | Win Rate | Avg Net |
| --- | ---: | ---: | ---: |
| +5m | 8 | 100.0% | +5.482% |
| +15m | 8 | 87.5% | +4.677% |
| +30m | 8 | 75.0% | +3.390% |
| +60m | 7 | 85.7% | +3.404% |
| EOD | 7 | 57.1% | +1.490% |

Two representative failures were not failed selections:

- `036930`: +5m +1.246%, +30m -1.152%, EOD -3.386%.
- `001210` on 2026-08-24: +5m +6.968%, +15m +4.363%, +30m -0.960%, EOD -1.752%.

The candidates produced immediate favorable excursion and then faded. This is evidence of horizon/exit mismatch, not evidence that Scanner selected dead symbols.

## 4. Candidate Setup Separates VWAP Pullback Quality

| VWAP Pullback Candidate Setup | N | +15m Avg | +30m Avg | EOD Avg |
| --- | ---: | ---: | ---: | ---: |
| DIRECTIONAL_BREADTH | 22 | +1.974% | +1.746% | +1.018% |
| LIQUIDITY_ONLY | 8 | -0.787% | -1.264% | -2.153% |
| UNCLASSIFIED | 4 | -1.028% | -1.191% | +0.976% |

Removing the best symbol from `VWAP pullback + DIRECTIONAL_BREADTH` leaves N=21, +1.051% average net and PF 2.86 at +30m.

The evidence does not support deprecating VWAP pullback. It supports distinguishing directional candidates from candidates promoted mainly by liquidity.

## 5. Scanner Score Calibration

Pearson correlation between Scanner total score and forward net return was weak:

| Horizon | Correlation |
| --- | ---: |
| +5m | 0.209 |
| +15m | 0.190 |
| +30m | 0.159 |
| EOD | 0.036 |

At +30m, the top score quartile averaged +1.748%, but the third quartile averaged -0.030%. Scanner total score has some top-tail information but is not monotonically calibrated.

The clearest winner-versus-loser component differences were higher trend, momentum, volume surge, MA alignment, and macro/chart fit. Trading-value contribution was higher in losers than winners in both immediate and HIGH cohorts.

### Candidate Source

| Source | N | +30m Avg | EOD Avg | Interpretation |
| --- | ---: | ---: | ---: | --- |
| top_value + top_volume | 14 | -0.593% | -1.436% | Repeatedly weak |
| top_volume only | 7 | +0.968% | +4.302% | Contributor-dependent |
| sector_theme | 25 | +0.184% | +0.289% | Near neutral |
| sector_theme + top_change_rate | 3 | +6.926% | +5.302% | Too small; one large winner |

Theme match by itself did not improve performance. The useful information was the combination of candidate setup and directional components, not the theme boolean alone.

## 6. BTC to Woori Technology Investment

| BTC Condition | N | +30m Win Rate | Avg Net | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| Ordinary bull | 12 | 66.7% | -0.059% | 0.84 |
| Strong bull | 7 | 71.4% | +1.547% | 24.77 |
| BTC 24h >= +5% | 3 | 100.0% | +3.586% | 999.00 |

Removing all 2026-08-21 strong-bull episodes leaves N=5, 60.0% wins, +0.229% average net, and PF 3.52. The effect weakens sharply but does not reverse.

Strong BTC is not an immediate +5m signal for Woori. Its best observed horizon was +30m. Ordinary BTC bullishness is rejected; only strong BTC plus Woori local confirmation remains a fixed shadow hypothesis.

## 7. Long-Horizon Concentration

| Horizon | N | Avg Net | Median | Without Best Symbol (`001210`) |
| --- | ---: | ---: | ---: | ---: |
| NEXT_OPEN | 107 | +0.971% | +0.132% | +0.336% excluding `005360` |
| D+1 30m | 107 | +1.476% | -0.061% | +0.442% |
| D+1 EOD | 107 | -0.050% | -0.500% | -1.125% |
| D+2 EOD | 105 | +0.153% | -0.280% | -1.930% |
| D+3 EOD | 101 | +1.624% | -1.254% | -1.104% |
| D+5 EOD | 88 | +2.531% | -0.600% | -0.926% |

The long-horizon averages are driven by a few explosive symbols. The median and leave-one-symbol results reject indiscriminate multi-day holding. Later reactivation must be treated as a new setup, not as justification to retain the original position.

## 8. Strategist LLM Contribution

The authoritative cumulative scorecard reports:

- Same-universe ranking overlay: 4,152 comparisons, average delta -0.0386 percentage points, NEUTRAL.
- Post-Scanner tactical refresh: 806 comparisons, average delta -0.4470 percentage points, DEGRADING.
- Full Strategist contribution: NOT_MEASURABLE because there is no strategy-neutral candidate-source control.

Additional observational splits show:

| Observation | N | +30m Avg | EOD Avg |
| --- | ---: | ---: | ---: |
| LLM changed pre-LLM playbook | 21 | +2.072% | -0.614% |
| LLM kept pre-LLM playbook | 54 | +0.689% | +0.201% |
| Cached/skipped market frame | 38 | +1.875% | -0.457% |
| Tactical refresh inherited frame | 37 | +0.256% | +0.414% |
| Non-default tactic selected | 8 | +4.249% | +0.794% |
| Default tactic selected | 67 | +0.697% | -0.125% |

These splits are confounded and do not prove LLM alpha. They do show that repeated Stage-2 refresh has not demonstrated value, while rare non-default choices identify a potentially stronger but very small cohort. LLM changes often coincide with short-lived +30m opportunity that does not survive to EOD, again pointing to horizon alignment rather than candidate selection alone.

## 9. What Is Actually Proven, Suggested, and Missing

### Strongest Existing Evidence

1. `HIGH + common_stock` separates short-horizon winners from ETF/non-common HIGH candidates.
2. Immediate common-stock Rank-1 alpha is concentrated in +5m to +15m and fades afterward.
3. VWAP pullback works materially better on `DIRECTIONAL_BREADTH` than `LIQUIDITY_ONLY` candidates.
4. `top_value + top_volume` is not a positive discriminator in the current sample.
5. Broad multi-day holding is invalid after contributor sensitivity.
6. Ordinary BTC bullishness is insufficient; strong BTC plus local confirmation is the narrower surviving hypothesis.

### Still Not Proven

1. Whether market regime further separates `HIGH + common_stock`; the latest canonical rebuild has only 13.2% point-in-time market snapshot coverage.
2. Whether the immediate common-stock result persists outside the August sample.
3. Whether HIGH is causal or only a proxy for trend/momentum/volume composition.
4. Whether Strategist Stage 1 adds value over a fully strategy-neutral Scanner universe.
5. Whether a profit-lock or a fixed +5m/+15m horizon is the better exit response.

## 10. Fixed Next Analysis Contract

Do not add more broad lanes. Use one joint cohort table with these flags:

- immediate within 60 seconds
- common stock / leveraged ETF / inverse ETF
- risk HIGH
- DIRECTIONAL_BREADTH / LIQUIDITY_ONLY
- scalp / intraday horizon
- trend, momentum, volume-surge component bands
- market snapshot and snapshot age

The first prospective shadow candidate should be:

> `common_stock AND risk_band=HIGH`, observed at +5m, +15m, +30m, and EOD, with no order or behavior effect.

The fixed comparison groups are:

1. HIGH common stock versus non-HIGH common stock.
2. HIGH common stock versus HIGH ETF/non-common assets.
3. HIGH common stock with and without DIRECTIONAL_BREADTH.
4. Immediate HIGH common stock versus later HIGH common stock.

The candidate should not be promoted until it has prospective observations across multiple market regimes and the market snapshot coverage gap is closed. The behavior patch, if later authorized, must choose one responsibility only: Scanner asset/setup suitability or Monitor short-horizon profit preservation, not both simultaneously.
