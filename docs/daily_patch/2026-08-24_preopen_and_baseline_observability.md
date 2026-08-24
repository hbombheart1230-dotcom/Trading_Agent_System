# 2026-08-24 Preopen and Baseline Observability

## Scope

This patch changes observability and shadow evaluation only. It does not alter
main Scanner, Strategist, Commander, Monitor, entry, exit, or order behavior.

## Changes

1. The scheduled preopen batch captures macro and market-index evidence before
   the preopen runtime. This prevents the first opening decision from depending
   on a macro snapshot created several seconds after that decision.
2. The Samsung/Hynix baseline is accumulated by corrected trading day from
   2026-08-21. One day is one independent sample; minute windows are retained as
   supporting measurements.
3. Q12 keeps its existing broad v2 record and adds
   `BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1`. The new shadow variant requires a
   BTC rise of at least 1.0% over 60 minutes or 3.0% over 24 hours, a positive
   leading signal, and Woori local price/volume confirmation.
4. A new independent `short_alpha_discriminator` reporting package joins the
   opening Rank-1 and canonical feature-mart artifacts by exact decision ID.
   It evaluates `HIGH_COMMON_SHORT_ALPHA_V1`, candidate setup, score calibration,
   profit fade, and Strategist Stage-2 ROI without changing agent authority.
5. Repeated windows are deduplicated to the first day-symbol observation before
   performance metrics are calculated. Historical discovery ends on 2026-08-24;
   prospective evidence begins on 2026-08-25.
6. Closeout maintenance now generates the short-alpha discriminator after the
   opening Rank-1 feature mart. This is a reporting-only step and cannot alter
   orders or agent authority.

## Evidence Gate

- The latest historical rebuild has 13.2% point-in-time market snapshot
  coverage. Promotion is blocked until prospective coverage reaches at least
  80%, even if historical short-horizon returns remain positive.
- Strategist Stage-2 authority removal is explicitly excluded from this patch.
  Its ROI remains an observational comparison only.

## Runtime Boundary

- No live process restart is required or performed during the 2026-08-24
  session.
- The preopen capture and Q12 variant become active on the next clean process
  start.
- No shadow result can create an `OrderIntent`.
- Strategist Stage-2 remains authoritative; only its before/after ROI is reported.
