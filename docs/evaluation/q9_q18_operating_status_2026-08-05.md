# Q9-Q18 Operating Status - 2026-08-05

## Authority

This document is the compact operating map for Q9 through Q18. It resolves the
phase-name ambiguity without reopening any closed evaluation.

| Program | Purpose | Status | Runtime consequence |
| --- | --- | --- | --- |
| Q9 | Full P/A/B/C multi-agent attribution | Diagnosis complete; evidence continues | Observation only |
| Q10 | Samsung/Hynix large-cap baseline | Control retained | Shadow only |
| Q11 | Opening surge and market-reversal baseline | Control retained | Shadow only |
| Q12 | BTC/Woori baseline | Control retained | Shadow only |
| Q13 | Attribution scores | Frozen | No formula or behavior change |
| Q14 | Scanner-alignment root cause | Frozen | No formula or behavior change |
| Q15 | Weak runner-up cascade restriction | Retain | Active defensive policy |
| Q16 | Directional evidence requirement | Closed `RETAIN` | Active defensive policy |
| Q17 | Horizon-matched directional-edge contract | Contract repaired | Natural-event smoke only |
| Q18 | Confirmed post-reclaim pullback promotion review | Closed `RETAIN SHADOW`; executable v0 rejected | No promotion |

## Q16 Authority Rule

The authoritative Q16 decision is the 2026-07-24 close decision: `RETAIN`.
Later proxy-rejection samples may update diagnostic metrics but cannot reopen or
reverse Q16. Any report displaying a different policy decision is reporting
drift, not a new promotion decision.

## Opening Research Identity

The prospective opening Rank-1 study that began with eligible day 2026-08-03
is not Q19. Its fixed program ID is:

`OPENING_ALPHA_VALIDATION_V1`

It is independent, shadow-only research. Q18 remains closed and no Q19 phase is
created.

## Current System Interpretation

The production system is defensive and low-frequency because several controls
operate in sequence:

1. Q15 removes weak runner-up fallback candidates.
2. Q16 requires directional evidence beyond ATR or volatility magnitude.
3. Commander rejects candidates above its risk budget.
4. Monitor still requires volume, maturity, structure, VWAP, and cost evidence.

This combination can correctly avoid weak trades, but it can also produce zero
entries when Scanner repeatedly ranks candidates that Commander cannot approve
or when opening moves complete before Monitor confirmation.

Do not respond by globally relaxing all guards. Separate three questions:

1. Candidate-policy compatibility: can the top-ranked instrument ever pass the
   Commander risk budget?
2. Opening opportunity: does a fixed opening cohort retain positive +15m/+30m
   net expectancy out of sample?
3. Monitor opportunity cost: do approved-but-blocked candidates outperform the
   cost floor after the relevant strategy horizon?

Only one behavior patch may follow a decision-ready result. All other changes
remain observability or independent shadow research.
