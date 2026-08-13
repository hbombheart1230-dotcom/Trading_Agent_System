# Rank-1 Fresh Change Activation Shadow

## Decision

`R1_FRESH_CHANGE_ACTIVATION_V1` is an independent observation-only contract.
It does not modify the fixed candidate contract created on 2026-08-11 and it
does not change Scanner ranking, Monitor entry/exit, Commander approval, or
order execution.

The candidate definition is deliberately narrow:

1. opening Rank-1
2. `scanner.source_top_change_rate == true`

Theme match, directional breadth, completed one-minute direction, VWAP,
recurrent rank, and quote quality are descriptive subgroups. They are not hard
gates during this collection window.

## Why This Contract Exists

The June-August reconstruction shows that `top_change_rate` presence is the
strongest train/validation-consistent separator currently available. Theme
match alone does not show an independent edge. Theme appears useful only as a
possible amplifier when fresh price activation is already present.

The evidence does not authorize production adoption. The historical result is
affected by a small sample, repeated symbols, and extreme winners. It requires
an untouched prospective comparison.

## Feature Mart Additions

The existing `rank1_feature_mart.v1` schema is extended additively with:

* canonical Strategist evidence
  * `market_playbook`
  * `tactical_strategy`
  * `tactical_subtype`
  * `strategy_scores`
  * `entry_horizon`
  * preferred themes and theme strength
* canonical Scanner evidence
  * `theme_match`
  * directional component count
  * candidate setup classification
* chart evidence provenance
  * computed completed-bar count
  * opening-shadow completed-bar count
  * minute-cache vs point-in-time fallback source
* execution observability
  * quote status
  * spread
  * tradability evidence status
  * missing execution fields

The Scanner source currently persists only the theme-match boolean for a
candidate. It does not persist the exact matched theme name. Therefore the mart
records `matched_theme_names_status=NOT_PERSISTED_BY_SOURCE`; it does not infer
or fabricate a theme name.

## ka10027 Point-in-Time Provenance

From 2026-08-12 onward, `top_change_rate` preserves the Kiwoom `ka10027`
response as observation-only provenance instead of retaining only the source
name.

Persisted evidence includes:

* source rank and capture time
* current price, previous-change sign and amount, and change rate
* sell orders, buy orders, and current volume
* execution strength and rank-entry count
* request filters and original response values

The same object passes through the Scanner source universe, ranking output, Q9
snapshot, Rank-1 feature mart, and fresh-change shadow. It does not affect a
Scanner score, candidate rank, Monitor decision, or order. Legacy rows without
the original response are labeled `NOT_CAPTURED_LEGACY`; values are never
backfilled by inference.

## Chart Fallback Rule

Fully closed cached minute bars remain authoritative. When the feature mart is
rebuilt before the current-day candle cache has been persisted, it may use only
the point-in-time values already stored in the opening shadow artifact.

Such rows are labeled:

`PARTIAL_OPENING_OBSERVATION_FALLBACK`

This fallback may restore completed-bar count, completed one-minute return, and
VWAP state when present. It must not invent moving-average, support, or
resistance states that cannot be reconstructed from bars.

## Frozen Prospective Window

* frozen at: 2026-08-12
* first eligible full day: 2026-08-13
* minimum independent matched sample: 5 day-symbols
* maximum collection duration: 10 valid trading days
* primary horizon: +15 minutes
* additional horizons: +5 minutes, +30 minutes, EOD
* live round-trip cost: inherited from the Rank-1 mart, 0.28%

Stop rules:

* 5 independent day-symbols: manual single-patch review becomes available.
* Fewer than 5 after 10 valid days: retain shadow and close this evaluation.
* Artifact failure: fix observability only; do not restart the contract unless
  the contract inputs were materially corrupted.
* No report automatically permits a behavior patch.

## 2026-08-12 Reconstruction Check

| Symbol | Setup | Top change | Theme match | Directional breadth | Completed bars | Evidence source |
| --- | --- | --- | --- | ---: | ---: | --- |
| 233740 | DIRECTIONAL_BREADTH | no | no | 5 | 0 | no completed bar at decision |
| 001210 | FRESH_CHANGE_ACTIVATION | yes | yes | 7 | 3 | opening point-in-time fallback |
| 483350 | LIQUIDITY_ONLY | no | no | 0 | 9 | opening point-in-time fallback |

The distinction explains the visible difference without changing behavior:
001210 had broad directional activation; 483350 was ranked mainly from
liquidity sources without directional confirmation.

## Strategist Interpretation

The feature mart now separates:

* `market_playbook`: the broad market frame selected by Strategist
* `tactical_strategy`: the Strategist tactical recommendation
* `scanner.candidate_setup`: the observed setup of the actual Rank-1 candidate

This prevents a broad `pullback` market frame from being mistaken for proof
that an individual candidate was itself a mature pullback. Future evaluation
can measure setup match without redefining Strategist or Scanner behavior.

The current evidence does not show that Strategist weighting adds alpha over
the intrinsic Scanner control. This remains an evaluation finding, not a prompt
or policy change.

## Artifacts

* `reports/evaluation/feature_mart/opening_rank1/feature_mart.json`
* `reports/evaluation/feature_mart/opening_rank1/integrity_report.json`
* `reports/evaluation/feature_mart/opening_rank1/fresh_change_activation/frozen_contract.json`
* `reports/evaluation/feature_mart/opening_rank1/fresh_change_activation/YYYY-MM-DD/fresh_change_activation_daily.json`
* `reports/evaluation/feature_mart/opening_rank1/fresh_change_activation/fresh_change_activation_cumulative.json`
* `reports/evaluation/feature_mart/opening_rank1/fresh_change_activation/fresh_change_activation_cumulative.md`

Normal closeout regenerates the mart and both prospective reports. The fresh
change contract remains separate from the two fixed candidates frozen on
2026-08-11.
