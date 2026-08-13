# Canonical Rank-1 Feature Mart

Date: 2026-08-11

## Decision

The next research unit is one canonical Rank-1 feature mart, not another independent extractor.
It reprocesses the retained June-August evidence under one point-in-time and cost contract.

This work is offline research only. It does not change Scanner ranking, Strategist output,
Monitor entry or exit behavior, Commander approval, or order execution.

## Priority 1: Build The Evidence Base Once

1. Freeze `rank1_feature_mart.v1`.
2. Normalize historical deep-dive and prospective opening-shadow episodes.
3. Recompute point-in-time chart state from bars fully closed by the decision time.
4. Compute one original-entry hold path at +5, +15, +30, +60, +120, +180, EOD,
   next open, D+1 30m, and D+1/D+2/D+3/D+5 EOD.
5. Apply the same 0.28% round-trip live cost to every outcome.
6. Audit duplicate IDs, symbol format, point-in-time leakage, feature coverage, and horizon coverage.

The chart contract distinguishes:

* opening intraday MA2/5 state
* intraday MA5/20 state when enough completed bars exist
* prior-day daily MA5/20 state
* VWAP position
* prior-day/opening-range support and resistance state
* existing chart-structure features

No completed bars means `INSUFFICIENT_EVIDENCE`; it is not interpreted as a weak chart.

## Priority 2: Assign Evidence To The Correct Owner

The same mart produces three independent, explainable trees.

| Tree | Question | Possible future owner |
| --- | --- | --- |
| Scanner suitability | Did a feature separate good Rank-1 symbols from weak Rank-1 symbols? | Scanner `lane_suitability` |
| Entry timing | Was the symbol sound but the decision-time chart state early or late? | Monitor trigger |
| Horizon suitability | Did the same entry work at one horizon and fail at another? | Strategist horizon evidence |

Example:

* If above-VWAP Rank-1 symbols outperform below-VWAP symbols at both +30m and EOD,
  the evidence belongs to Scanner suitability.
* If both groups reach similar EOD returns but below-VWAP entries suffer larger early MAE,
  the evidence belongs to Monitor timing.
* If a chart state is positive at +15m but negative at EOD, it belongs to horizon selection,
  not to a universal Scanner penalty.

## Fixed Analysis Order

1. Build the canonical mart.
2. Reprocess all retained June-August episodes.
3. Pass integrity and coverage checks.
4. Generate Scanner, Entry, and Horizon trees from the same rows.
5. Require direction agreement between pre-August training and August validation.
6. Retain at most two branches as prospective shadow candidates.
7. Observe those candidates without changing trading behavior.
8. If evidence passes, change exactly one responsible component.

Stage 7 is implemented by `rank1_fixed_candidate_prospective_shadow_2026-08-11.md`.
Its candidate selection is frozen through 2026-08-11; later mart rows update outcomes only.

Broad Rank-1 entry, unconditional golden-cross entry, and unconditional longer holding are not candidates.

## Outputs

The reproducible output root is:

`reports/evaluation/feature_mart/opening_rank1/`

It contains the schema, full mart, monthly JSONL partitions, integrity report,
three responsibility trees, horizon matrix, and candidate selection artifact.

Regenerate with:

`venv\\Scripts\\python.exe scripts\\run_rank1_feature_mart.py`

Refresh retained Kiwoom research candles before regeneration with:

`venv\\Scripts\\python.exe scripts\\run_rank1_feature_mart.py --refresh-sources --refresh-from 2026-08-01 --base-day 2026-08-11`

## Current Limitation

Decisions made before 09:01 have no fully completed one-minute candle. Their intraday chart state
must remain `INSUFFICIENT_EVIDENCE`; later candles must not be backfilled into the decision feature.
The integrity report therefore distinguishes raw coverage from eligible-sample coverage.
Missing or ineligible chart history is never an alpha feature.
