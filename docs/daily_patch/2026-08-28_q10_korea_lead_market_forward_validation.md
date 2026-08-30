# 2026-08-28 Q10 Korea Lead-Market Forward Validation

## Scope

- Added a prospective-only Q10 extension for Samsung Electronics, SK Hynix,
  KOSPI, and KOSDAQ.
- Added immutable 08:50 KST lead-market snapshots and fixed rule-based states.
- Added Korean market reaction checkpoints, expected-versus-actual labels,
  and cost-adjusted shadow entry comparisons.
- Added a prospective cumulative report starting on `2026-08-31`.
- Added the 08:50 slot to the opening macro collector.
- Added activation-aware readiness checks for the preopen snapshot and all
  Q10 lead-market closeout artifacts.

## Safety

- No historical backfill or backtest.
- No threshold optimization or ML.
- No main Scanner, Strategist, Monitor, Commander, entry, exit, or execution
  behavior changed.
- No `OrderIntent` or Executor connection exists in the experiment.
- Measurement failures are isolated from the original Q10 baseline.

## Verification

- Forward-validation and existing Q10/opening collector tests pass.
- Full regression: `2676 passed, 1 skipped`.
- Snapshot immutability, missed-window behavior, deterministic scoring,
  reaction classification, cost application, and execution isolation are
  covered by tests.
