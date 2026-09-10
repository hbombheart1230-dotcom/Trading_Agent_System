# 2026-09-10 Evaluation Closeout Integrity

## Scope

This patch changes evaluation and reporting integrity only. It does not change
Scanner ranking, Strategist behavior, Commander approval, Monitor entry/exit
rules, position sizing, or broker execution.

## Corrected Issues

1. The `TRD_20260910_024060_01` broker result remains authoritative at
   `+15.05%`, while exit-quality and horizon attribution are excluded because a
   stale expected-exit quote affected the holding path before the runtime fix.
   Selection and entry evidence remain eligible.
2. Alpha Research Board companion files are generated directly from their
   authoritative builders. Canonical Board schema remains frozen.
3. Q9 closeout minute recovery is persisted under the daily evaluation bundle
   and reused by artifact inventory and day validity.
4. Unified Q9 versus Samsung/Hynix comparison requires comparable evidence only
   for shared horizons. `+120m` and `+180m` remain visible as baseline-only.
5. Operator summaries prefer the active Commander horizon over stale nested
   post-exit placeholders.
6. Artifact inventory recognizes `post_exit_shadow_recap.json`, and symbol
   `024060` has the fallback display name `흥구석유`.

## Rebuilt Result

- Q9 day status: `VALID`
- Complete P/A/B/C windows: `411`
- Forward candidates: `3628`
- Forward observed: `3593`
- Forward usable coverage: `99.67%`
- Unified comparison: `COMPLETE`
- Alpha Research Board integrity: `PASS`
- Horizon incident exclusions: `1`

## Verification

- Focused regression: `125 passed`
- Full regression: `3059 passed, 1 skipped`
