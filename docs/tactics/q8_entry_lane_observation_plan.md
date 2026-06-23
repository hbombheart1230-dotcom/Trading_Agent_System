# Q8 Entry Lane Observation Plan

Status: COMPLETED / SUPERSEDED FOR ACTIVE SCHEDULING

The lane definitions remain valid historical Q8 evidence definitions. The
Q8 evaluation window was closed by
`../evaluation/q8_final_comprehensive_review_2026-06-20.md`.
The "next 3 to 5 live sessions" language below describes the original review
plan and is not a current instruction. Continued lane artifacts feed Q9
through `../evaluation/current_operating_baseline.md`.

Purpose: collect enough observation-only evidence to decide whether the current
entry blocks are correctly filtering weak setups or over-blocking tradable
setups.

This plan does not authorize new trading behavior. It only defines how to read
the expanded Q8 shadow surface.

## Scope

Every shadow candidate should carry `entry_lane_observation`.

Required fields:

- `primary_lane`
- `subtype`
- `time_bucket`
- `market_regime`
- `cost_floor_state`
- `reason`
- `primary_failure_axis`
- compact feature snapshot

Current primary lanes:

- `vwap_reclaim`
- `pullback_quality`
- `volume_confirmation`
- `breakout_readiness`
- `opening_momentum`
- `opening_largecap_surge`
- `runner_up_selection`
- `human_chart_sanity`
- `cost_edge`
- `confirmed_or_other`

## Why All Lanes Are Split Now

The earlier approach split one blocker at a time. That avoided behavior risk,
but it made evaluation slow when live trade count was low.

The new approach splits all major lanes at the observation layer only.

This means:

- runtime behavior is unchanged
- entry and exit guards are unchanged
- Q8 can compare blocked candidates across all lanes immediately
- later behavior promotion can still happen one policy at a time

## Evaluation Window

Historical Q8 plan: use the next 3 to 5 live sessions as the first review
window. This window has completed.

Daily review should answer:

1. Which lane blocked the most candidates?
2. Which lane subtype had positive forward outcome despite being blocked?
3. Which lane subtype correctly blocked weak forward outcomes?
4. Which time bucket produced the best missed opportunities?
5. Did the result depend on market regime?
6. Were runner-up candidates actually inferior to the selected candidate?

## Minimum Evidence

Directional review can begin when a lane subtype has:

- 50 or more shadow observations, or
- 20 or more forward-outcome observations with a clear average-return skew, or
- repeated same-day evidence across at least 3 sessions.

Behavior promotion still follows `promotion_framework.md`.

## First Promotion Targets

Do not promote all changes at once.

Expected review order:

1. `vwap_reclaim` subtypes
2. `pullback_quality` subtypes
3. `breakout_readiness` subtypes
4. `opening_momentum` and `opening_largecap_surge`
5. `runner_up_selection`
6. `volume_confirmation`

## Current Rule

If the live trade count remains low, Q8 should rely on shadow candidates and
forward outcomes for pre-entry policy review.

If artifact integrity is broken, pause promotion and repair artifacts first.
