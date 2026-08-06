# Integrated Trade Diagnosis Fixed Plan

## Scope

This work unifies existing evidence without changing Scanner, Strategist,
Monitor, Commander, order execution, entry rules, or exit rules.

The implementation reuses:

- Q9 trade read models and trade evaluations
- Q13/Q14 lineage and horizon fields embedded in those models
- prospective opening Rank-1 shadow artifacts
- opening Rank-1 deep-dive and longitudinal outputs
- broker-authoritative realized returns

## Completed Offline Reconstruction

Period: 2026-06-01 through 2026-07-31

Outputs:

- `trade_thesis_rows.json`: one row per reconstructed trade
- `symbol_day_sequences.json`: one row per day and symbol
- `opening_policy_counterfactuals.json`: opening policy decisions
- `integrated_trade_diagnosis.json`: unified metrics and readiness
- `historical_reprocessed_report.md`: human-readable summary
- `prospective_validation_status.json`: fixed three-day gate

Lineage confidence is explicit:

- `EXACT`: a Q9 decision ID connects the trade to the decision chain
- `TIME_MATCHED`: stages exist but no exact Q9 ID connects the trade
- `INFERRED`: only partial surrounding evidence exists
- `UNKNOWN`: no defensible connection exists

Missing evidence is never converted into a negative result or an inferred
policy outcome.

## Policy Comparisons

### Opening

- `CURRENT_PIPELINE`
- `OPENING_PROBE`
- `WAIT_CONFIRM`
- `NO_CHASE`

The historical `OPENING_PROBE` reconstruction uses only first-five-minute and
breakout-framing evidence. Historical VWAP evidence was not consistently
persisted, so rows with missing VWAP are marked `PARTIAL_MISSING_VWAP`.
Prospective artifacts must preserve VWAP and completed-bar evidence rather
than backfilling them from future candles.

### Same-Symbol Reentry

- `CURRENT`
- `STOP_AFTER_FIRST_EXIT`
- `FRESH_EPISODE_ONLY`
- `PROFIT_LOCK`

The first two are reconstructable from historical trades. The latter two stay
`INSUFFICIENT_EVIDENCE` until independent-setup provenance and executable
profit-lock prices are persisted prospectively.

### Horizon and Exit

Only persisted horizon contracts and post-exit checkpoints are used. A missing
checkpoint is not treated as evidence that holding longer failed.

### D+1 to D+5 Reactivation

Later highs are separated from durable closes. A later high alone does not
prove that a point-in-time reactivation trigger existed before the move.

## Prospective Validation

> Schedule note (2026-08-06): this three-day period was an integration and artifact
> verification gate. It is closed and must not be used as the current promotion
> schedule. The authoritative five-session decision boundary is defined in
> `canonical_execution_plan_2026-08-06.md`.

Start: 2026-08-03

Duration: three full trading days. The period is fixed and is not extended for
small samples.

A no-trade day is valid when the opening Rank-1 cohort and its 30-minute
forward observations are complete. A day is invalid only for an observability
defect such as:

- opening policy row count mismatch
- non-exact lineage for an executed trade
- missing horizon contract for an executed trade
- missing opening 30-minute forward observation

Fixing an observability defect does not reset already valid days. Source data
is regenerated and the day is re-evaluated.

Run after market close:

```powershell
.\venv\Scripts\python.exe scripts\run_integrated_trade_validation.py `
  --day YYYY-MM-DD `
  --start 2026-06-01 `
  --validation-start 2026-08-03
```

## Decision Gate

After three valid days, select exactly one behavior patch.

This sentence is retained as historical plan context. Candidate selection now follows
the evidence outcomes and five-session boundary in the canonical execution plan.

Current leading historical candidate: `OPENING_PROBE`.

The candidate is not production policy until the prospective artifacts prove
that its point-in-time conditions and forward outcomes are complete. Reentry,
horizon, reactivation, and opening behavior must not be changed together.
