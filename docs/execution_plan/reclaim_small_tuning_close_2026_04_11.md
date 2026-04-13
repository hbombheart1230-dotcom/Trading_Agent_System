# Reclaim Small Tuning Close - 2026-04-11

## Why This Tuning
Entry blocker analysis showed that family-level counts were not enough to choose the next tuning target safely. After breaking families down into raw blockers, `below_vwap_reclaim_not_ready` stood out as the most appropriate first small-tuning candidate.

Why this blocker first:
- `005930` was primarily constrained by reclaim/VWAP readiness and produced `BUY 0` on the day-level drilldown.
- `000660` looked more constrained by breakout confirmation and cooldown timing than reclaim.
- `011930` looked closer to scanner-selected quality / extension suspicion than reclaim readiness.

That made `below_vwap_reclaim_not_ready` the best single raw blocker to adjust first.

## What Changed
This change only touches reclaim readiness handling for the raw blocker `below_vwap_reclaim_not_ready`.

Scope:
- breakout-style policy-aware reclaim relaxation only
- only when the legacy blocker is `below_vwap_reclaim_not_ready`
- only for a slightly widened near-ready band
- only when supporting evidence remains intact

Tuning version:
- `small_relaxation_v1`

Operational meaning:
- the reclaim gate is still active
- the gate is not removed or inverted
- the tuned-only band is slightly wider than the previous standard near-ready band
- the tuned-only band still requires supporting volume confirmation

## What Did Not Change
The following were intentionally left untouched:
- `pullback_not_mature`
- `breakout_not_ready`
- `volume_confirmation_missing`
- `post_exit_cooldown`
- `too_extended_from_vwap`
- scanner ranking
- strategist policy
- exit policy
- execution guard

This remains a conservative, additive tuning.

## Provenance / Observability
The tuning now leaves explicit runtime traces in monitor artifacts.

Primary fields:
- `entry_policy_aware_gating.entry_tuning_flags`
- `entry_policy_aware_gating.reclaim_readiness_tuned`
- `entry_policy_aware_gating.reclaim_tuning_version`
- `entry_policy_aware_gating.reclaim_tuning_scope`
- `entry_policy_aware_gating.reclaim_tuning_band_used`
- `entry_policy_aware_gating.reclaim_evidence_explanation`

Normalized blocker surface fields:
- `entry_blocker_surface.below_vwap_reclaim_not_ready`
- `entry_blocker_surface.reclaim_gate_ok`
- `entry_blocker_surface.vwap_hold_ok`
- `entry_blocker_surface.vwap_reclaim_ok`
- `entry_blocker_surface.reclaim_distance_to_ready`
- `entry_blocker_surface.reclaim_readiness_tuned`
- `entry_blocker_surface.reclaim_tuning_version`
- `entry_blocker_surface.reclaim_tuning_scope`
- `entry_blocker_surface.reclaim_tuning_band_used`
- `entry_blocker_surface.entry_tuning_flags`
- `entry_blocker_surface.reclaim_evidence_explanation`

These fields make it possible to compare pre/post tuning runs without changing the existing canonical/report layout.

## Why Raw Blocker Instead Of Family-Level Tuning
Family counts were useful to localize the problem, but they still mixed multiple mechanisms together. `pullback_timing` and `reclaim_readiness` each contained different raw blockers with different operational meanings.

This change therefore stays at the raw blocker level:
- tune only `below_vwap_reclaim_not_ready`
- leave the rest of the family untouched

## Next Candidates
If this reclaim-only adjustment proves useful and does not create chase-style entries, the next raw blockers to inspect are:
1. `pullback_not_mature`
2. `breakout_not_ready`
3. `volume_confirmation_missing`

Those remain next-step candidates only. They were not tuned in this change.

## Remaining Limits
- Some symbols may still stay blocked when reclaim is genuinely too weak.
- This change does not solve scanner-selected quality issues.
- This change does not solve cooldown or breakout confirmation delay.
- This is still an analysis-led, conservative runtime change rather than a broad entry retune.
