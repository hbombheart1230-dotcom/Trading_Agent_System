# Promotion Framework

Purpose: define how an experimental observation becomes an official trading
policy.

This framework is documentation only. It does not change runtime behavior,
strategy options, execution logic, monitor behavior, guard thresholds,
Strategist prompts, or report generation.

## Promotion Lifecycle

```text
Observation
  -> Validation
  -> Evaluation
  -> Promotion Candidate
  -> Controlled Adoption
  -> Official Policy
  -> Ongoing Review
  -> Retain / Adjust / Deprecate
```

Lifecycle definitions:

| Stage | Meaning | Exit Requirement |
| --- | --- | --- |
| Observation | A pattern, defect, or opportunity is noticed in live, report, shadow, or feedback evidence. | The observation is recorded with source artifacts. |
| Validation | Confirm the observation is trustworthy and not caused by missing or inconsistent artifacts. | Artifact integrity passes or gaps are documented. |
| Evaluation | Measure whether the observation is useful, harmful, or neutral. | Metrics compare the observation against a baseline. |
| Promotion Candidate | The observation has enough evidence to justify a possible behavior change. | A promotion review is written. |
| Controlled Adoption | The rule is applied with limited scope, clear rollback criteria, and continued measurement. | Controlled adoption shows benefit without unacceptable regression. |
| Official Policy | The rule becomes part of the documented trading policy. | Policy docs and ownership boundaries are updated. |
| Ongoing Review | The official rule is monitored for decay, regime sensitivity, or side effects. | Periodic scorecards confirm continued usefulness. |
| Retain / Adjust / Deprecate | The rule is kept, revised, or removed based on evidence. | Decision is traceable to reviews and scorecards. |

## Section 1: Experimental Categories

All experimental categories follow the same promotion process. No category can
skip validation and evaluation.

| Category | Observation Examples | Required Baseline |
| --- | --- | --- |
| Shadow Candidates | blocked candidates later outperform selected trades | selected candidate or current policy |
| Runner-Up Selection | runner-up substitutions outperform or underperform top candidates | Scanner Top-1 and original selected candidate |
| Cost Floor Rules | cost floor blocks weak trades or misses good trades | current cost floor policy |
| Pullback Quality Rules | immature pullbacks fail, mature pullbacks improve outcomes | current entry policy |
| Volume Confirmation Rules | volume confirmation improves timing or filters false moves | current volume handling |
| Exit Aggression Policies | `intraday_low_break` or VWAP exits occur too early or too late | current exit policy |
| Overnight Policies | carry decisions help or harm next-day outcomes | intraday-only baseline and current carry policy |
| Hold Policies | extended hold avoids profit fade or increases drawdown | current hold/exit behavior |
| Strategist Recommendations | scenarios, sector preferences, or recommendation types add value | raw Scanner behavior |
| Reporter Feedback | feedback adoption improves later decisions | feedback-disabled or pre-feedback baseline |
| Market Regime Rails | market context rails improve tactic selection or risk control | same-day current policy by market regime |
| News Event Intelligence | event/theme/symbol watch evidence improves candidate interpretation | scanner candidates without news-event watch evidence |

The category determines the evidence source, not the promotion standard.

## Section 2: Promotion Eligibility Criteria

Promotion must be evidence-driven.

Minimum eligibility requirements:

- artifact completeness is sufficient to reconstruct affected trades
- broker truth, lifecycle truth, and report truth have no unresolved critical
  conflicts
- comparison baseline is defined before promotion
- sample size is documented
- live trades and shadow observations are separated
- observation-only fields are not treated as production behavior
- expected benefit is larger than transaction cost and operational risk
- downside risk and opportunity cost are measured
- no unresolved defect explains the apparent improvement

Suggested minimum evidence thresholds:

| Evidence Type | Minimum Guideline |
| --- | --- |
| Live closed trades | Prefer 20 or more comparable trades before strong promotion decisions |
| Shadow observations | Prefer 50 or more comparable candidate observations for directional confidence |
| News event observations | Prefer multiple event types and enough linked/unlinked candidates to compare false positives and missed opportunities |
| Trading days | Prefer multiple market regimes or at least several live days |
| Artifact integrity | No `BLOCKER` issues; `WATCH` issues must be documented |
| Baseline comparison | Current policy, Scanner Top-1, or feedback-disabled baseline must be available |

Metrics to evaluate:

- trade count
- win rate
- expectancy
- profit factor
- average return
- average loss
- maximum drawdown
- opportunity cost
- risk-adjusted improvement
- side-effect rate

Promotion should not rely on one attractive example. A rule that looks
reasonable but does not improve measured outcomes remains experimental.

## Section 3: Shadow vs Production Comparison

Every promotion candidate should compare current behavior against an alternate
policy.

Example:

```text
Current Policy
vs
Shadow Policy
```

Comparison metrics:

| Metric | Current Policy | Shadow Policy | Delta | Notes |
| --- | ---: | ---: | ---: | --- |
| Trade count |  |  |  |  |
| Win rate |  |  |  |  |
| Expectancy |  |  |  |  |
| Profit factor |  |  |  |  |
| Drawdown |  |  |  |  |
| Average return |  |  |  |  |
| Average loss |  |  |  |  |
| Opportunity cost |  |  |  |  |

Comparison rules:

- Use the same decision windows where possible.
- Separate realized trade results from shadow-only outcomes.
- Mark missing forward outcomes explicitly.
- Treat shadow results as evidence, not as final proof.
- Compare against the actual policy active at the time.
- Include opportunity cost when a filter blocks trades.

## Section 4: Promotion Decision Classes

Use standardized decision classes for every review.

| Decision | Meaning | Required Evidence | Next Action |
| --- | --- | --- | --- |
| `PROMOTE` | Evidence supports turning the candidate into policy. | Sufficient sample, positive baseline delta, acceptable drawdown, clean artifact integrity. | Move to controlled adoption or official policy depending on risk. |
| `RETAIN UNDER OBSERVATION` | Signal is plausible but not proven. | Some positive evidence but insufficient sample or mixed market regimes. | Continue collecting evidence without behavior changes. |
| `ADJUST AND RE-TEST` | Idea has value but the rule definition is too broad, narrow, early, or late. | Mixed evidence with identifiable failure mode. | Revise the experimental definition and restart evaluation. |
| `REJECT` | Candidate does not improve outcomes. | Neutral or negative baseline delta with enough evidence. | Stop treating it as an active promotion candidate. |
| `DEPRECATE` | Existing official policy appears harmful or stale. | Negative performance, recurring regression, or risk increase after official adoption. | Remove or downgrade policy through a controlled change review. |

## Section 5: Promotion Review Template

Use this structure for every promotion decision.

### Summary

What was tested?

### Evidence

- sample size:
- time period:
- live trade count:
- shadow observation count:
- artifact integrity status:
- baseline:
- metrics:

### Benefits

Observed improvements:

- win rate:
- expectancy:
- profit factor:
- drawdown:
- opportunity cost:
- risk-adjusted improvement:

### Risks

Observed regressions:

- missed opportunities:
- larger average loss:
- worse drawdown:
- lower trade count:
- market-regime sensitivity:
- artifact gaps:

### Recommendation

Decision class:

- `PROMOTE`
- `RETAIN UNDER OBSERVATION`
- `ADJUST AND RE-TEST`
- `REJECT`
- `DEPRECATE`

### Rationale

Detailed explanation:

- why the evidence is sufficient or insufficient
- what baseline was used
- what changed after comparison
- what risks remain
- what must be monitored next

## Section 6: Strategist Promotion Framework

Strategist recommendations require a separate promotion review because they
can add reasoning complexity without improving trade outcomes.

Examples to evaluate:

- scenario effectiveness
- recommendation effectiveness
- sector preference effectiveness
- overnight recommendation effectiveness
- runner-up substitution effectiveness
- market-regime interpretation effectiveness

Core questions:

- Did the recommendation improve results?
- Did it reduce risk?
- Did it outperform raw Scanner behavior?
- Did it improve candidate selection or only explain it?
- Did it reduce exposure to recurring failure patterns?
- Did it create missed opportunity cost?

Strategist promotion comparison:

| Review Area | Baseline | Promotion Evidence |
| --- | --- | --- |
| Scenario effectiveness | same trades grouped without scenario preference | scenario has positive expectancy and acceptable drawdown |
| Recommendation effectiveness | Scanner Top-1 or current policy | recommendation improves expectancy or risk-adjusted result |
| Sector preference effectiveness | sector-neutral scanner ranking | sector preference improves selection quality |
| Overnight recommendation effectiveness | intraday-only baseline | carry improves next-day outcome without excess drawdown |

Strategist recommendations should not become official policy unless they show
measurable value beyond Scanner output.

## Section 7: Feedback Promotion Framework

Reporter feedback requires its own promotion path because feedback can be
correct in wording but ineffective in future decisions.

Lifecycle:

```text
Feedback generated
  -> Feedback adopted
  -> Performance measured
  -> Feedback effectiveness scored
  -> Retain / Adjust / Deprecate
```

Metrics:

| Metric | Meaning |
| --- | --- |
| Adoption rate | how often future Strategist decisions reflect the feedback |
| Usefulness score | combined score of adoption, performance delta, pattern reduction, and evidence quality |
| Performance delta | outcome change after feedback adoption |
| Pattern reduction | reduction in the targeted bad behavior |
| Side-effect rate | good trades missed or new failure patterns caused by feedback |

Feedback review table:

| Feedback Type | Recommendation Count | Adoption Rate | Performance Delta | Usefulness Score | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
|  |  |  |  |  |  |

Retention criteria:

- feedback is traceable to later Strategist decisions
- adoption improves outcomes or reduces risk
- side effects are acceptable
- usefulness score remains positive across review windows
- evidence is not dominated by one isolated example

## Section 8: Governance Rules

No tactic becomes official policy solely because it appears reasonable.

Governance requirements:

- Promotion requires evidence.
- Promotion decisions must be traceable.
- Promotion decisions must reference evaluation reports.
- Promotion decisions must reference scorecards.
- Strategist-related promotions must reference Strategist effectiveness reviews.
- Feedback-related promotions must reference Feedback effectiveness reviews.
- Critical artifact integrity issues must be resolved before promotion.
- Every promoted policy needs an ongoing review condition.
- Every official policy must have a retain, adjust, or deprecate path.

Required references for a promotion decision:

- intraday validation notes
- artifact integrity audit
- trade evaluation output
- daily scorecard
- Strategist effectiveness review when applicable
- Feedback effectiveness review when applicable
- promotion review template

The system should evolve through measured evidence rather than ad-hoc
modifications.
