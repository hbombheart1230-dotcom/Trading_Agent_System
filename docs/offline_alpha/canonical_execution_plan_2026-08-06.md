# Offline Alpha Canonical Execution Plan

## Authority

This document is the operating schedule for the post-reconstruction offline alpha work.
It resolves the older three-day integration check, the five-session decision window,
and the separate 25-episode/10-day broad Rank-1 promotion gate.

No item in this plan authorizes an order or changes Scanner, Strategist, Commander,
Monitor, entry, exit, sizing, or execution behavior.

Schedule status after 2026-08-07 is governed by
`active_research_register_2026-08-07.md`. This document remains authoritative for
the frozen definitions of the three opening lanes.

## What Is Complete

- June-July integrated historical reconstruction
- detailed opening Rank-1 casebook
- conditional 5m/15m/30m/60m/EOD horizon comparison
- stage lineage comparison from intrinsic Scanner Rank-1 through execution
- historical D+1-D+5 delayed-reactivation replay
- broad prospective `OPEN_0_20_RANK1_30M` artifact generation

The completed offline work is not repeated or expanded with another broad search.

## Three Separate Hypotheses

| Lane | Point-in-time definition | Primary historical horizon | Meaning |
| --- | --- | ---: | --- |
| `IMMEDIATE_OPENING_PROBE` | intrinsic Rank-1 within the first 60 seconds | 15m | immediate opening continuation |
| `CONFIRMED_RECURRENT_RANK` | prior Rank-1 observation in 5m plus a positive completed 1m return | 30m | candidate survives opening noise and confirms |
| `DISLOCATION_REBOUND` | market or symbol dislocation with non-extreme volume | 60m | rebound after a sharp dislocation |

These lanes are observer labels. They do not alter membership of the frozen broad
Rank-1 control cohort.

`LATENT_REACTIVATION_WATCH` is separate. It watches an initially failed Rank-1 for
D+1 through D+5 and records a new Scanner reappearance plus fresh volume, VWAP, or
breakout evidence. It never means carrying the original position.

## Schedule

### Closed: Three-Day Integration Check

The old three-day gate verified that historical reconstruction and daily artifacts
could be generated. That engineering check is closed and is not a promotion window.

### Closed: Five-Session Decision Window

- sessions: 2026-08-03 through 2026-08-07, assuming regular market sessions
- purpose: select at most one next behavior-patch candidate
- no extension of the whole analysis after the fifth session
- no threshold or lane changes during the window
- no behavior changes during collection

The window closed on 2026-08-07. The final decision is recorded in
`five_session_closure_2026-08-07.md`. It is not extended.

An episode counts for a lane only when the lane's point-in-time evidence is present.
A broad opening Rank-1 episode does not automatically count as a recurrent-rank or
dislocation episode.

Decision at the close of the fifth session:

| Result | Decision |
| --- | --- |
| at least 5 new eligible episodes and direction agrees with historical evidence | choose one behavior-patch candidate |
| fewer than 5 eligible episodes | retain only that lane in shadow; close the other analysis work |
| prospective direction opposes historical evidence | reject the candidate |
| artifact defect | repair measurement only; do not change strategy rules |

An unrecoverable artifact defect does not cause an open-ended extension. The affected
lane is reported as `INSUFFICIENT_EVIDENCE` and the five-session review still closes.

### Background Control: 25 Episodes and 10 Days

The existing `OPEN_0_20_RANK1_30M` broad control keeps its frozen promotion gate:

- at least 25 observed +30m episodes
- at least 10 observed trading days
- existing quality and concentration gates unchanged

This background control does not delay the five-session candidate-selection decision.
Passing it authorizes controlled shadow review only, not live execution.

## Historical Behavior-Patch Priority

### Priority 1: Confirmed Recurrent Rank Preservation

If the five-session evidence agrees with the historical direction, the first patch
candidate is narrow candidate preservation:

1. intrinsic Scanner Rank-1 is observed repeatedly,
2. a completed one-minute return is positive,
3. point-in-time volume and execution evidence are usable,
4. the candidate remains available for downstream evaluation.

Preservation is not automatic entry. It does not bypass cost, chart, portfolio,
risk, or execution checks.

### Priority 2: Latent Reactivation Candidate Reinjection

This may be considered only after prospective D+1-D+5 watch evidence shows that a
fresh trigger appeared before the later move. Reinjection means returning the symbol
to candidate evaluation at the new timestamp. It is not overnight holding and is not
applied together with recurrent-rank preservation.

### Not First Priority

- broad opening gate relaxation
- unconditional opening probe
- unconditional longer holding
- generic Commander or Monitor bypass
- simultaneous opening, horizon, and reactivation changes

## Daily Artifacts

- `reports/evaluation/opening_rank1_shadow/YYYY-MM-DD/opening_rank1_shadow_daily.json`
- `reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json`
- `reports/evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_watch.json`
- `reports/evaluation/opening_rank1_shadow/five_session_review/opening_alpha_five_session_review.json`

Daily review records:

- lane eligibility and missing evidence
- exposure direction and asset class when available
- execution-evidence state and spread observation
- 5m/15m/30m/60m/EOD outcomes
- latent-watch redetection and fresh-signal evidence

## Current Integrity Status

As of 2026-08-06:

- 2026-08-03: `VALID`, 6 episodes
- 2026-08-04: `VALID`, 4 episodes
- 2026-08-05: `ARTIFACT_INCOMPLETE`; opening Q9 universes were absent until 09:16
- 2026-08-06: `VALID`, 4 episodes

The 2026-08-05 source gap must not be converted into a valid early-opening result.
If no authoritative source can reconstruct it, its affected lanes remain insufficient.

## Final Boundary

At the five-session close, the system must produce one of four outcomes for each lane:

- `SELECT_BEHAVIOR_CANDIDATE`
- `RETAIN_LANE_SHADOW_ONLY`
- `REJECT_CANDIDATE`
- `INSUFFICIENT_EVIDENCE_ARTIFACT_DEFECT`

Exactly one behavior candidate may be selected. All other broad analysis work closes.

The final selection was `NONE`. The current work queue is latent fresh-trigger
forward attribution followed by same-symbol provenance; neither changes behavior.
