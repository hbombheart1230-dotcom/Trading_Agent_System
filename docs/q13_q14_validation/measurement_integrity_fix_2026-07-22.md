# Measurement Integrity Fix - 2026-07-22

## Scope

This patch corrects evaluation and reporting only. It does not change Scanner,
Strategist, Commander, Monitor, entry, exit, or order behavior.

## Corrections

### Commander C semantics

Commander C previously reused the Strategist B candidate return even when the
Commander rejected the candidate. Commander C now represents the actual policy:

- approved window: candidate forward return minus evaluation cost
- rejected/no-trade window: cash return of 0

The Samsung/Hynix baseline uses different decision windows, so its return delta
is now labelled an unpaired descriptive comparison. It is not reported as
causal Commander alpha.

### Forward observation states

The 2026-07-22 source contains 4,273 P-role candidates:

- 2,697 with at least one observed forward checkpoint
- 301 with legitimate pending checkpoints
- 1,275 without collected minute rows

The last group is now `unavailable`, not `invalid`. Missing observation coverage
still remains visible and can invalidate a day when no trusted comparison
override exists. Actual stale, contradictory, or malformed evidence remains
`invalid`.

### Q16 proxy-only rejection evidence

Q16 now has a dedicated cumulative report:

- `q16_proxy_rejection_review.json`
- `q16_proxy_rejection_review.md`

New shadow records preserve the full `entry_cost_filter`, allowing exact
classification of proxy-only rejections. Historical cost rejections lacking
those fields are reported separately as legacy unattributed rows and cannot be
used for RETAIN/ROLL_BACK.

### Daily Summary runtime activity

When explicit daily counters are absent, Daily Summary now aggregates the full
day Q9 decision windows before falling back to a short live-summary lookback.
It reports Commander approvals, blocks, noops, and Monitor BUY/NOOP counts from
the actual decision records.

## Validation Rule

Today's raw artifacts are retained and may be regenerated. Q16 Day 1 remains
`INSUFFICIENT_EVIDENCE` when exact proxy-only fields are absent; legacy rows are
context only and are never silently promoted to exact evidence.
