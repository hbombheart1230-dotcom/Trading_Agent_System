# Strategist Effectiveness Review

Purpose: measure whether Strategist decisions create measurable value through
scenario quality, strategy-guided Scanner influence, and post-Scanner refresh.

This document defines evaluation methodology only. It does not change runtime
strategy, scanner selection, monitor behavior, guard logic, prompt content, or
execution behavior.

## Core Question

Does the Strategist improve trading results, or does it merely add complexity
after the Scanner has already identified the opportunity set?

The runtime invokes Strategist before Scanner. Therefore a same-pool
`scanner_intrinsic_control` is not a fully raw pre-Strategist baseline: candidate
sourcing may already reflect Strategist guidance. The review must keep the
following comparisons separate:

- scenario/horizon proposal versus subsequent market behavior;
- same-universe intrinsic ranking versus strategy-weighted ranking;
- first Scanner result versus an optional post-Scanner Strategist refresh;
- future shadow-only strategy-neutral Scanner versus the production
  strategy-guided Scanner.

Only the final comparison can estimate the Strategist's complete incremental
contribution. Until it exists, do not label the full Strategist positive or
negative from the same-universe ranking control.

## Required Inputs

- Scanner candidate ranking at decision time
- Final selected candidate
- Strategist scenario and recommendation fields
- Commander selection reason
- Entry quant decision
- Exit quant decision
- Trade lifecycle and broker truth
- Shadow candidate outcomes where available
- Operator summary and trade report artifacts

## Q1: How Do Strategist Scenarios Perform?

Group closed trades by Strategist scenario.

Example scenarios:

- `semiconductor_strength`
- `ai_momentum`
- `defensive_rotation`
- `market_risk_off`
- `theme_continuation`
- `liquidity_leader`
- `opening_momentum`
- `risk_reduction`

Metrics per scenario:

| Metric | Definition |
| --- | --- |
| Trade count | number of closed trades linked to the scenario |
| Win rate | winning trades / closed trades |
| Average return | average realized PnL percent |
| Average loss | average realized PnL percent for losing trades |
| Profit factor | gross profit / absolute gross loss |
| Expectancy | average expected return per trade after losses |
| MDD | maximum peak-to-trough drawdown within the scenario sample |

Scenario review table:

| Scenario | Trades | Win Rate | Avg Return | Avg Loss | Profit Factor | Expectancy | MDD | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |  |  |  |

Status values:

- `retain`: scenario shows positive expectancy and acceptable drawdown.
- `watch`: sample is small or mixed.
- `adjust`: scenario has useful signal but poor timing, sizing, or exit quality.
- `deprecate_candidate`: scenario repeatedly underperforms and adds no clear
  value over Scanner baseline.

## Q2: Does Strategist Outperform Raw Scanner Ranking?

Compare observable ranking influence for each decision window:

- A: same-universe intrinsic Scanner Top-1
- B: strategy-weighted Scanner Top-1

The comparison should use paired shadow/forward outcomes. It measures the
strategy weighting overlay only. It does not measure candidate-source effects
because Strategist ran before both rankings.

Comparison metrics:

| Metric | Formula |
| --- | --- |
| Win rate delta | Strategist final win rate - Scanner Top-1 win rate |
| Expectancy delta | Strategist final expectancy - Scanner Top-1 expectancy |
| Profit factor delta | Strategist final profit factor - Scanner Top-1 profit factor |
| Drawdown delta | Strategist final MDD - Scanner Top-1 MDD |

Decision review table:

| Window | Intrinsic Same-Universe Top-1 | Strategy-Weighted Candidate | Observable Strategist Influence | Intrinsic Outcome | Weighted Outcome | Value Add |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

Value Add values:

- `positive`: strategy-weighted candidate outperformed the same-universe intrinsic control.
- `neutral`: final candidate was similar to baseline.
- `negative`: final candidate underperformed baseline.
- `unknown`: missing baseline or forward outcome evidence.

Evaluation rules:

- If the strategy weighting overlay repeatedly moves away from the intrinsic
  same-universe Top-1 and produces negative expectancy delta, that overlay is
  `DEGRADING`.
- Do not generalize this result to the full Strategist without a neutral
  candidate-source control.
- Evaluate post-Scanner Strategist refresh separately from the initial frame.

## Q3: Which Strategist Recommendations Consistently Fail?

Track recommendation types independently from broad scenario names.

Examples:

- `gap_up_chase`
- `late_day_momentum`
- `overnight_hold`
- `low_volume_rebound`
- `theme_stock_rotation`
- `runner_up_substitution`
- `vwap_reclaim_pullback`
- `opening_momentum_probe`
- `defensive_observe`

Failure pattern table:

| Recommendation | Trades | Win Rate | Expectancy | Failure Pattern | Evidence |
| --- | ---: | ---: | ---: | --- | --- |
|  |  |  |  |  |  |

Recurring failure patterns to detect:

- entry after the main move is already extended
- volume confirmation missing or fading
- pullback not mature before entry
- cost floor passed mechanically but target range too small
- late-day entry with insufficient time to work
- overnight recommendation without carry-quality evidence
- theme linkage weak or unrelated to selected symbol
- runner-up selected without independent suitability

Recurring success patterns to detect:

- intrinsic and strategy-weighted Scanner Top-1 agree under a successful scenario
- strong theme plus volume confirmation
- pullback quality improves before entry
- cost floor has sufficient target buffer
- exit avoids large profit fade
- shadow candidates underperform the selected candidate

## Q4: Retain, Adjust, Or Deprecate Strategist Rules

Each Strategist rule or recommendation type should be assigned one of:

- `retain`
- `adjust`
- `deprecate_candidate`
- `insufficient_evidence`

Evaluation criteria:

| Decision | Criteria |
| --- | --- |
| Retain | positive expectancy, profit factor above 1.0, acceptable MDD, and positive or neutral Scanner delta |
| Adjust | signal appears useful but timing, confirmation, cost buffer, or exit quality is weak |
| Deprecate candidate | negative expectancy, weak Scanner delta, recurring failure pattern, and enough sample evidence |
| Insufficient evidence | sample too small or artifacts incomplete |

Minimum evidence guideline:

- Do not retain or deprecate a rule from a single trade.
- Prefer at least 20 comparable observations for directional conclusions.
- If live trades are scarce, use shadow candidate and forward outcome evidence
  to support but not fully replace realized trade evidence.

## Output Schema Target

Future read-only review output may use this shape:

```json
{
  "schema_version": "strategist_effectiveness_review.v1",
  "day_or_window": "",
  "evaluation_mode": "read_only",
  "scenario_scorecards": [],
  "scanner_vs_strategist": {
    "win_rate_delta": null,
    "expectancy_delta": null,
    "profit_factor_delta": null,
    "drawdown_delta": null
  },
  "recommendation_patterns": [],
  "retain_adjust_deprecate": [],
  "insufficient_evidence": [],
  "artifact_gaps": []
}
```

## Boundary

This review can recommend future investigation. It must not directly change:

- Strategist prompts
- strategy options
- scanner ranking
- commander approval
- entry rules
- exit rules
- guard thresholds
- broker execution
