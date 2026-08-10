# Offline Alpha Active Research Register

## Authority

This register is the current work queue after the fixed five-session close.
When an older contract or generated report conflicts with this register, use:

1. `five_session_closure_2026-08-07.md` for the closed-window decision.
2. this register for current work and stopping rules.
3. `canonical_execution_plan_2026-08-06.md` for frozen lane definitions.
4. older contract/result documents as historical evidence only.

No item below changes Scanner, Strategist, Commander, Monitor, entry, exit,
sizing, orders, or execution unless a later promotion decision explicitly says so.

## Cost Authority

Every new evaluation must show both bases without mixing them:

- live-equity research basis: 0.28% round trip before any separately stated slippage;
- mock-observed basis: broker cost profile, shown with its sample count and source;
- ETF/ETN tax assumptions must be identified by instrument type;
- gross, live net, and mock net must be separate fields.

## Closed Work

- H1-H3: rejected.
- H4, H6-H9: rejected; H5 was not testable with retained evidence.
- post-reclaim executable policy v0: rejected.
- broad opening Rank-1 behavior: rejected by the fixed five-session result.
- Monitor-NOOP review: complete; retain current Monitor gates.
- five-session behavior patch: none; P3 is not activated.

Closed work is not extended, retuned, or renamed into a new phase.

## Active Priority 1: Latent Reactivation Fresh Trigger

Purpose: determine whether a failed Rank-1 symbol can be captured later from a new,
point-in-time signal rather than by carrying the old position.

Required observation unit:

`initial failed Rank-1 -> first fresh D+1-D+5 trigger -> next tradable minute -> forward path`

Required outputs:

- trigger timestamp, rank, score, signal evidence, and reference entry;
- +5m, +15m, +30m, +60m, and EOD return/MFE/MAE;
- gross, live-net, and mock-net results;
- unique initial watch and unique day-symbol concentration;
- explicit missing-price and stale-observation reasons.

Decision point: 12 independent fresh-trigger outcomes. Before 12, status is
`COLLECTING`. The old position is never carried and no order is generated.

Initial reconstruction on 2026-08-07:

- raw fresh signals: 6;
- excluded because the trigger day was `ARTIFACT_INCOMPLETE`: 3;
- eligible fresh triggers: 3;
- completed +30m outcomes: 2;
- current status: `COLLECTING`.

Artifacts:

- `reports/evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.json`
- `reports/evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.md`

## Active Priority 2: Same-Symbol Sequence Provenance

Purpose: separate exhausted-move repetition from a genuinely new setup.

Collect automatically:

- immutable day-symbol sequence and trade ordinal;
- prior/current entry and exit, realized return, cumulative return, peak return,
  giveback amount and ratio;
- prior/current decision and setup identifiers where available;
- elapsed time and fresh VWAP, breakout, volume, market, theme, and horizon evidence;
- integrity status when exact provenance is unavailable.

Decision point: 10 clean profit-exit reentry opportunities. Loss-conditioned
same-day reentry remains blocked and is not retested.

Initial reconstruction from 2026-06-01 through 2026-08-07:

- day-symbol sequences: 76;
- repeated sequences: 18;
- clean profit-exit reentries still possible under the current loss block: 2;
- current status: `COLLECTING`.

Artifacts:

- `reports/evaluation/same_symbol_sequences/YYYY-MM-DD/same_symbol_sequence.json`
- `reports/evaluation/same_symbol_sequences/same_symbol_sequence_cumulative.json`

## Background Observation

The following continue automatically but do not delay active work:

- `IMMEDIATE_OPENING_PROBE`;
- `CONFIRMED_RECURRENT_RANK`;
- `DISLOCATION_REBOUND`;
- frozen broad opening Rank-1 control;
- VWAP-reclaim blocked cohort.

Background results cannot change behavior without a separate fixed contract and
promotion review.

The three opening lanes retain their existing definitions and thresholds. Normal
closeout maintenance refreshes their daily/cumulative artifacts. No new opening lane
or broad validation window is created.

## Single-Patch Rule

Whichever reaches its decision point first is reviewed first. At most one behavior
candidate can proceed. If it fails, close it. Do not compensate by changing another
threshold in the same review.
