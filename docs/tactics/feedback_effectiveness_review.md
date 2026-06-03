# Feedback Effectiveness Review

Purpose: measure whether Reporter -> Strategist feedback improves future
decisions and trading results.

This document defines evaluation methodology only. It does not change runtime
strategy, prompts, report generation, execution logic, monitor logic, or guard
behavior.

## Core Question

Does feedback from trade reports and daily reviews help the Strategist make
better future decisions?

The feedback loop should be treated as a measurable intervention. A feedback
item is valuable only if it is adopted in future decisions and improves
outcomes or reduces exposure to known bad patterns.

## Required Inputs

- Reporter feedback items
- Strategist input packets
- Strategist scenario and recommendation outputs
- Scanner candidate pool
- Final candidate selection
- Entry and exit quant decisions
- Trade lifecycle and broker truth
- Shadow candidate outcomes
- Daily scorecard output when available

## Q1: Feedback Disabled vs Feedback Enabled

Compare periods or decision windows where feedback was not used against periods
or windows where feedback was available to the Strategist.

Metrics:

| Metric | Definition |
| --- | --- |
| Win rate | winning trades / closed trades |
| Expectancy | average expected return per trade |
| Profit factor | gross profit / absolute gross loss |
| MDD | maximum peak-to-trough drawdown |
| Average return | average realized PnL percent |

Comparison table:

| Mode | Trades | Win Rate | Expectancy | Profit Factor | MDD | Avg Return |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Feedback disabled |  |  |  |  |  |  |
| Feedback enabled |  |  |  |  |  |  |
| Delta |  |  |  |  |  |  |

Evaluation rule:

Feedback is useful only if the enabled period shows better or more stable
results after controlling for market regime and sample quality.

## Q2: Feedback Adoption Quality

Each feedback item should be tracked from recommendation to future Strategist
behavior.

Example feedback:

```text
avoid gap-up chase
```

Adoption questions:

- Did the Strategist reduce gap-up chase exposure?
- Did the Strategist explicitly acknowledge the risk?
- Did the final candidate selection avoid that pattern?
- Did later performance improve?
- Did the system simply avoid trades without improving selectivity?

Adoption table:

| Feedback ID | Feedback | Target Pattern | Opportunities | Adopted | Adoption Rate | Later Performance Delta |
| --- | --- | --- | ---: | ---: | ---: | ---: |
|  |  |  |  |  |  |  |

Adoption quality values:

- `high`: Strategist behavior changed in the intended direction and outcomes improved.
- `medium`: behavior changed but performance effect is unclear.
- `low`: feedback was visible but not reflected in future decisions.
- `harmful`: feedback was adopted and performance worsened.
- `unknown`: insufficient evidence.

## Q3: Feedback Categories

Track feedback by category so the system can learn which feedback types are
useful.

Categories:

- `entry_quality`
- `exit_quality`
- `overnight_quality`
- `hold_quality`
- `scanner_quality`
- `theme_quality`
- `cost_edge_quality`
- `runner_up_quality`
- `risk_management`

Category table:

| Category | Recommendation Count | Adoption Count | Adoption Rate | Performance Delta | Usefulness |
| --- | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |

Performance delta should be calculated against comparable trades or shadow
opportunities before and after the feedback item became available.

## Q4: Feedback Usefulness Scoring

Each feedback item should eventually receive a usefulness score.

Example target output:

```json
{
  "feedback_id": "",
  "category": "entry_quality",
  "target_pattern": "gap_up_chase",
  "adoption_rate": 0.72,
  "performance_delta": 0.18,
  "usefulness_score": 0.81
}
```

Suggested scoring components:

| Component | Meaning |
| --- | --- |
| Adoption rate | how often future Strategist decisions reflect the feedback |
| Performance delta | outcome change after adoption |
| Pattern reduction | whether bad exposure decreased |
| Side-effect penalty | whether the feedback caused excessive missed opportunities |
| Evidence quality | artifact completeness and sample size |

Illustrative formula:

```text
usefulness_score =
  0.30 * adoption_rate
+ 0.35 * normalized_performance_delta
+ 0.20 * pattern_reduction
+ 0.15 * evidence_quality
- side_effect_penalty
```

The formula is a future evaluation target. It is not a trading rule.

## Failure Modes To Detect

- feedback is present but ignored by the Strategist
- feedback is adopted too broadly and suppresses good trades
- feedback reduces one bad pattern but creates another
- feedback repeats generic advice without measurable behavior change
- feedback conflicts with Scanner evidence or market regime
- feedback cannot be traced to later decisions

## Output Schema Target

Future read-only review output may use this shape:

```json
{
  "schema_version": "feedback_effectiveness_review.v1",
  "day_or_window": "",
  "evaluation_mode": "read_only",
  "feedback_enabled_vs_disabled": {
    "win_rate_delta": null,
    "expectancy_delta": null,
    "profit_factor_delta": null,
    "mdd_delta": null,
    "avg_return_delta": null
  },
  "feedback_items": [],
  "category_scorecards": [],
  "usefulness_scores": [],
  "harmful_feedback_candidates": [],
  "insufficient_evidence": [],
  "artifact_gaps": []
}
```

## Boundary

This review may identify valuable, useless, or harmful feedback types. It must
not directly change:

- Strategist prompts
- Strategist option set
- scanner selection
- commander approval
- monitor entry or exit rules
- guard thresholds
- report generation
- broker execution
