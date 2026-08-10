# Agent Effectiveness Scorecard Framework

Date: 2026-08-07

Status: CURRENT EVALUATION AUTHORITY

## Purpose

This document fixes how the system decides whether Scanner, Strategist,
Commander, Monitor Entry, and Monitor Exit add measurable value.

It does not add a new evaluation axis. It joins the existing Q9, Q13/Q14,
strategy-horizon, Quant Trade Diagnosis, shadow, and offline-alpha evidence
under one component decision table.

The business question is:

```text
Which component preserves trading edge, which component destroys it, and which
component still cannot be measured from trustworthy evidence?
```

This framework is reporting and evaluation authority only. It does not change
Scanner weights, Strategist prompts, Commander authority, Monitor rules,
position sizing, orders, or execution.

## Why This Is Needed

The current system already records many useful surfaces:

- Quant Trade Diagnosis explains one completed trade.
- Q13 records attribution axes.
- Q14 decomposes Scanner alignment root causes.
- strategy-horizon evidence compares intended and actual holding behavior.
- Q9 shadows preserve candidates that were not traded.
- offline-alpha research tests conditional opportunities.
- same-symbol evidence measures repeated-entry damage.

These surfaces answer different questions. They must not be averaged into one
opaque blame score. They must feed one fixed component scorecard so that the
evaluation produces decisions instead of another open-ended observation phase.

## Fixed Decision Chain

Evaluate one immutable decision window through the actual runtime chain:

```text
market snapshot
  -> Commander operating context
  -> Strategist initial market/strategy frame
  -> strategy-guided Scanner candidate sourcing and ranking
  -> optional post-Scanner Strategist tactical refresh
  -> optional Scanner rerun
  -> Monitor candidate and entry eligibility
  -> Commander/decision approval or veto
  -> actual entry
  -> actual exit and pinned horizon
  -> broker-authoritative net outcome
```

The same `decision_id`, symbol, timestamp, cost basis, and forward-price source
must be used across comparisons. A narrative symbol match is not sufficient.

## Three Separate Tests

Every component receives three separate checks.

### 1. Contract Correctness

Did the code execute its documented responsibility without schema, timestamp,
symbol, arithmetic, or authority errors?

Examples:

- Scanner rank is deterministic from the persisted inputs.
- Strategist context is applied once and the resulting ranking is retained.
- Commander approves or vetoes but does not silently invent a candidate.
- Monitor uses the pinned position horizon and valid candle data.
- broker truth remains authoritative for realized PnL.

Passing this check means the code followed its contract. It does not mean the
contract is profitable.

### 2. Economic Value

Did the component improve cost-adjusted outcomes relative to the input it
received?

This requires a paired counterfactual. Standalone win rate is not enough.

### 3. Evidence Quality

Can the comparison be trusted?

Required evidence classes remain separate:

- `REALIZED`
- `TRUSTED_SHADOW`
- `RECONSTRUCTED`
- `UNAVAILABLE`

Reconstructed evidence may support direction but cannot silently become
realized evidence.

## Standard Component States

Each component receives exactly one current state.

| State | Meaning | Required next action |
|---|---|---|
| `NOT_MEASURABLE` | The paired comparison or required evidence is unavailable. | Repair only the named evidence gap. Do not wait without a named gap. |
| `DEFECT` | The implementation violated its fixed contract. | Fix the defect, exclude contaminated observations, and validate only the affected component. |
| `DEGRADING` | The component repeatedly worsened its input baseline after costs. | Select one explainable root cause for a behavior-patch review. |
| `NEUTRAL` | The component produced no meaningful improvement or degradation. | Retain only if operationally necessary; do not claim alpha. |
| `VALUE_ADD` | The component repeatedly improved the paired baseline after costs. | Retain; promotion still follows the Promotion Framework. |

Do not assign a low score when evidence is missing. Use `NOT_MEASURABLE`.

## Fixed Component Scorecard

### Scanner

Question:

```text
Did Scanner include worthwhile candidates and rank the stronger forward
outcomes above weaker alternatives?
```

Required comparisons:

- Top-1 versus Top-3, Top-5, and Top-10 means
- rank-bucket monotonicity
- candidate universe versus omitted source leaders where preserved
- gross, live-net, and mock-net +5m/+15m/+30m/+60m/EOD outcomes
- results by market regime, source, time bucket, tactic compatibility, and
  repeated-rank status

Scanner is `VALUE_ADD` only when ranking precision is positive after costs. A
weak-market Top-1 is not automatically a good absolute opportunity.

Scanner is evaluated conditional on the strategy frame it actually received.
The current `scanner_intrinsic_control` removes Strategist ranking-weight
effects inside the same candidate universe, but candidate sourcing may already
reflect Strategist source and theme policy. It is therefore not a fully raw,
pre-Strategist Scanner.

### Strategist

Question:

```text
Did the Strategist produce a useful market/strategy frame, and did each
observable Strategist influence improve the downstream Scanner result?
```

The Strategist must be evaluated in three separate parts:

```text
1. scenario and horizon proposal vs subsequent market/trade behavior
2. same-universe intrinsic Scanner ranking vs strategy-weighted ranking
3. first Scanner result vs result after an optional post-Scanner Strategist refresh
```

Part 2 measures only the marginal ranking-overlay effect. It does not measure
the Strategist's full contribution because the candidate universe may already
have been sourced under Strategist guidance.

The full Strategist contribution requires a parallel, shadow-only neutral
Scanner control whose candidate sourcing and ranking do not consume Strategist
policy. Until that control exists, full Strategist value is `NOT_MEASURABLE`.

For observable paired effects, measure symbol-change rate, win-rate delta,
average-return delta, expectancy delta, profit-factor delta, MDD delta, and
no-trade protection. Group results by scenario, playbook, horizon, risk tone,
market rail, and recommendation.

If historical strategy-option scores were not persisted, they remain
`UNAVAILABLE`. Do not infer them from report prose.

### Monitor Entry

Question:

```text
Did Monitor enter a selected opportunity at a better point than immediate
entry, or correctly block an inferior opportunity?
```

Required comparisons:

- selected-candidate price at decision time
- earliest policy-eligible entry
- actual entry
- blocked/no-entry outcome
- delay, +5m/+15m/+30m forward return, MFE, MAE, and cost-adjusted edge
- blocker-level outcomes for volume, VWAP, pullback, breakout, and cost gates

Monitor Entry must be judged separately for executed and blocked candidates.
Few realized trades do not prevent evaluation when trusted blocked-candidate
forward outcomes exist.

### Commander

Question:

```text
Did Commander approval or veto improve the candidate it received?
```

Required paired comparison:

```text
candidate presented to Commander
vs Commander-approved result or veto shadow result
```

Commander is not credited for Scanner ranking and is not blamed for a symbol
change produced before its decision. An approval is not value add by itself;
the approved candidate must outperform the veto/no-trade baseline. A veto adds
value only when it avoids a cost-adjusted loss.

### Monitor Exit And Horizon

Question:

```text
Did the actual exit preserve more strategy-valid value than the available
horizon alternatives?
```

Required comparisons:

- actual broker-net exit
- pinned BUY-time minimum, target, and maximum horizon
- MFE and MAE before exit
- hard invalidation and stop-first path
- actual exit versus +5m/+15m/+30m/+60m/EOD or strategy-specific checkpoints
- post-exit MFE, MAE, peak-to-exit fade, and target-hold improvement

A later high does not prove an early exit was wrong. `EXIT_TOO_EARLY` requires
that the later path was executable, did not breach the strategy stop first,
and improved the result after costs.

## Evidence Thresholds

Reuse the fixed Q9 thresholds. Do not create a new calendar whenever a result
is inconvenient.

| Decision strength | Minimum evidence |
|---|---|
| Directional | 20 paired observations, 2 valid days, at least 90% integrity |
| Promotion candidate | 50 paired observations, 3 valid days, at least 95% integrity, cost-positive effect |
| Strong policy decision | 100 paired observations, 5 valid days, at least 2 market regimes |

When the threshold is not met, publish the available direction and exact
shortfall. Do not reset historical valid observations. Only contaminated rows
are excluded.

## Worked Examples

### Example 1: Strategy ranking overlay degrades the same universe

At 09:05 the Strategist has already produced the strategy frame. Scanner ranks
the same candidate universe twice for evaluation: the intrinsic control ranks
A first and the applied strategy-weighted ranking places B first.

| Candidate | +30m live-net return |
|---|---:|
| same-universe intrinsic A | +1.20% |
| strategy-weighted B | +0.30% |

Diagnosis:

- Scanner's intrinsic ranking may have selection value for this window.
- The observable strategy ranking-overlay delta is `-0.90%p`.
- Commander is not blamed if it merely approved B.
- The trade result alone must not be labelled a Monitor failure.

Repeated paired results like this make the ranking-overlay contribution
`DEGRADING`. They do not prove that the complete Strategist is degrading,
because its earlier candidate-source influence has no independent neutral
control. The next action is to identify the responsible context adjustment,
not to rewrite the whole pipeline.

### Example 2: Monitor correctly blocks a weak candidate

Scanner and Strategist agree on C, but Monitor blocks it for missing volume.
C subsequently returns `-1.10%` after costs.

Diagnosis:

- Scanner/Strategist still produced a weak opportunity.
- Monitor Entry added defensive value.
- This is evidence to retain the volume gate, even though no real trade exists.

### Example 3: Monitor kills a valid opportunity

Candidate D passes the strategy context but Monitor blocks it for VWAP reclaim.
The trusted forward path is `+2.00%`, with small MAE and sufficient volume.

Diagnosis:

- Monitor Entry may be `DEGRADING` for this blocker subtype.
- One case is not enough to relax the gate.
- Accumulate paired cases under the same blocker definition and market regime.

### Example 4: A later high does not prove early-exit failure

The system exits E at `-0.40%`. E later reaches `+1.00%`, but first falls
through the strategy stop to `-2.00%`.

Diagnosis:

- The later high was not a valid continuous-hold counterfactual.
- The exit can be `EXIT_DEFENSIVE_VALID`.
- A fresh later signal belongs to latent reactivation research, not horizon
  extension.

### Example 5: Valid early-exit problem

An intraday position has a 5-minute minimum and a 30-minute target. It exits
after 40 seconds for a minor VWAP fluctuation, no hard invalidation is present,
the stop is never breached, and the +30m live-net return is `+1.40%`.

Diagnosis:

- Contract correctness is reviewed first.
- If the exit reason was not authorized before minimum hold, mark `DEFECT`.
- If the contract allowed it but repeated outcomes lose value, mark Monitor
  Exit `DEGRADING` and review one horizon-specific exit rule.

## Current Baseline Assessment

This is a bounded assessment from currently retained evidence, not a permanent
policy decision.

| Component | Current state | Current evidence |
|---|---|---|
| Scanner relative ranking | `DEGRADING` | The broad 2026-06-01 through 2026-07-29 full-chain range does not meet the fixed ranking-effect contract. A bounded opening subgroup remains positive but does not override the broad result. |
| Scanner absolute edge | `DEGRADING` | Broad candidate cohorts remain weak after cost. |
| Strategist full contribution | `NOT_MEASURABLE` | Strategist runs before Scanner; no fully independent strategy-neutral candidate-source control exists. |
| Strategist ranking overlay | `NEUTRAL` | Broad range: 3,542 paired +30m windows across 25 days, average delta +0.0917 percentage points and positive-window rate 12.65%; the fixed positive or negative materiality contract is not met. The earlier 65-case subgroup does not represent full-range overlay behavior. |
| Strategist post-Scanner refresh | `NOT_MEASURABLE` | First-pass versus refreshed Scanner outcomes require exact refresh-linked paired coverage. |
| Monitor Entry | `NEUTRAL` | The broad full-chain review retained current entry timing; this does not prove entry alpha. Small positive blocked subtypes remain unresolved. |
| Commander | `NEUTRAL` | 4,461 paired windows across 25 days are measurable but do not meet the fixed positive materiality rate. |
| Monitor Exit/Horizon | `NOT_MEASURABLE_AFTER_FIX` | Historical early-exit defects exist; corrected runtime lacks enough completed live trades. |
| Full system | `DEGRADING` | The broad broker-net positive-edge hypothesis was rejected for the analyzed range. |
| Same-symbol loss reentry | `DEGRADING` | Repeated entries after loss materially underperform; the existing loss block remains supported. |
| Opening conditional lanes | `COLLECTING` | Conditional signals remain shadow evidence; broad opening Rank-1 behavior is rejected. |
| Latent reactivation | `COLLECTING` | Fresh-trigger evidence has not reached the fixed decision point. |

These labels describe evidence maturity. They do not authorize behavior
changes.

## Operating Plan

### Step 1: Freeze The Questions

Do not add more agent axes or Q-numbered evaluation programs. Use the five
component questions in this document.

### Step 2: Build One Cumulative Scorecard

Join existing artifacts into one authoritative range view. Each row must show:

- decision ID and evidence class
- Strategist frame, Scanner input universe, ranking overlay, optional refresh,
  and final candidate as separate stages
- paired cost-adjusted outcomes
- integrity status and exclusion reason
- component state and supporting evidence links

Quant Trade Diagnosis remains the per-trade explanation. The cumulative
scorecard is the cross-trade decision surface.

Implementation status: `IMPLEMENTED_2026_08_07`.

Artifacts:

- daily: `reports/evaluation/agent_effectiveness/YYYY-MM-DD/`
- cumulative baseline: `reports/evaluation/agent_effectiveness/2026-07-29/`
- JSON: `agent_effectiveness_scorecard.json`
- Markdown: `agent_effectiveness_scorecard.md`

The Q9 daily pipeline writes the current day increment. Historical cumulative
rebuilds are explicit off-hours jobs because raw forward reconstruction is too
expensive to repeat in every daily closeout.

### Step 3: Reuse Historical Evidence

Use all trustworthy historical rows. Do not restart because a new artifact was
added. Mark unavailable fields honestly and count only comparable pairs for the
affected component.

### Step 4: Continue Only Named Evidence Collection

Current active collection remains:

- latent reactivation fresh-trigger outcomes to 12 independent cases;
- clean profit-exit same-symbol reentry opportunities to 10 cases;
- existing opening lanes in the background.

These collections fill named counterfactual gaps. They do not create new
evaluation axes or extend closed broad opening studies.

### Step 5: Make One Component Decision

When a component reaches its evidence threshold, assign one standard state.
If it is `DEGRADING`, select one root cause and prepare one behavior-patch
candidate. Do not modify multiple agents in the same comparison window.

### Step 6: Compare Before And After With The Same Scorecard

The scorecard definition, cost basis, horizon, and evidence class remain fixed.
Only the patched component receives a new validation window. Other component
history remains valid.

## Stop Rules

Evaluation stops being open-ended under these rules:

- Reaching the fixed threshold requires a decision, including rejection.
- Failing to reach a threshold does not reopen closed research.
- `NOT_MEASURABLE` must identify a concrete missing join or artifact.
- Poor results do not justify extending a fixed window.
- A promising subgroup may continue only under a separately named, fixed
  counterfactual contract.
- At most one behavior patch proceeds from a completed review.

## Authority Relationships

- `q9_full_chain_evaluation_matrix.md` owns fixed component comparisons and
  evidence thresholds.
- `quant_trade_diagnosis_report_plan.md` owns the per-trade explanation.
- `integrated_selection_horizon_sequence_evaluation_2026-07-31.md` owns the
  joined selection, horizon, reactivation, and same-symbol interpretation.
- this document owns the standard component states and cumulative decision
  process.
- `promotion_framework.md` owns the final transition from evidence to policy.
- `active_research_register_2026-08-07.md` owns the current bounded research
  queue and stopping points.

When an older narrative conflicts with this framework, preserve it as
historical context but use this framework for current component status.
