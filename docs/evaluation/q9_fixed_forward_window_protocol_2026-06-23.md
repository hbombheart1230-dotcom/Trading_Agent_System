# Q9 Fixed Five-Trading-Day Forward Window Protocol

Effective date: 2026-06-23

## Status

- Q9 direction: retained
- Q9 observability enhancement: complete
- 2026-06-23: instrumentation/application day, excluded from the formal sample
- Formal Day 1: the next full regular-session trading day
- Formal window length: five valid trading days

The window is counted by actual full regular-session trading days, not calendar
days. A holiday, shortened session, failed startup, or materially incomplete
Q9 artifact day does not count as a valid day.

## Frozen Runtime Boundary

During the five-day window, do not modify:

- entry rules, gates, thresholds, or sizing
- exit rules, confirmation, thresholds, or hold behavior
- Scanner sourcing, filtering, ranking, or weighting behavior
- Strategist prompts, schemas, routing, cache behavior, or recommendations
- Commander approval, veto, routing, or risk-control behavior
- execution and order behavior

Q9 remains read-only. No observed result authorizes an intraday behavior patch.

## Permitted Fixes

Only measurement defects may be corrected:

- missing Q9 artifacts
- additive schema fields that fail to persist
- P/A/B/C linkage failures
- forward price observation failures
- invalid timestamps, duplicate rows, or broken decision IDs
- deterministic aggregation or report-rendering defects
- schema validation defects

A permitted fix must not change which symbol is selected, whether an order is
approved, entry timing, exit timing, quantity, or order type.

If a measurement fix changes the meaning of previously collected evidence,
only the affected day or affected component sample is invalidated. The entire
Q9 program is not restarted automatically.

## Daily Post-Close Review

After every valid session, record:

1. P/A/B/C decision-window counts
2. forward observation completion rate
3. Top-1, Top-3, Top-5, and Top-10 performance
4. candidate-source performance
5. root-cause distribution
6. whether `insufficient_sample` remains unresolved

Required horizons:

- +5 minutes
- +15 minutes
- +30 minutes
- EOD

Top-K and source performance must show:

- gross return
- broker-cost-adjusted return
- slippage-adjusted return
- observation count
- observed trading-day count

## Valid-Day Gate

A day is valid only when:

- the runtime covered the full regular session
- daily Q9 artifacts exist
- the additive Q9 schema is valid
- at least 20 P/A/B/C windows exist
- at least 95% of Scanner decision windows have linked P/A/B/C rows
- selected candidates are present where selection occurred
- at least 95% of forward candidate rows are observed or have an explicit
  legitimate pending reason
- no unresolved artifact-integrity blocker changes the interpretation

A day with zero executed trades can still be a valid Q9 day. Trade execution
is not required for Scanner, Strategist, Commander, shadow-candidate, or
forward-outcome evaluation. Monitor entry, Monitor exit, and realized-system
samples remain insufficient until actual trades occur.

Synthetic/test rows are excluded from the formal sample and reported as a
warning. A small number of invalid forward rows are excluded from the affected
component sample. They invalidate the whole day only when usable forward
coverage falls below 95%.

The canonical validity artifact is:

- `reports/evaluation/daily/YYYY-MM-DD/q9_day_validity.json`

Its final post-close status is `VALID` or `INVALID`. During the session it is
`IN_PROGRESS`; this is not a failed day.

## Day-One Operational Checkpoints

For each formal evaluation day:

1. 09:10 KST: confirm runtime heartbeat, Q9 schema, and fresh P/A/B/C linkage.
2. 12:00 KST: confirm linkage ratio and forward observation growth.
3. 15:35 KST or after Kiwoom regular-session close confirmation: generate the
   final Q9 evaluation and inspect `q9_day_validity.json`.

If a measurement defect is found intraday, repair the measurement path only.
Preserve already valid rows. Do not discard the full day unless the final
validity artifact is `INVALID`.

## Decision Timing

- No policy decision is made before five valid days are complete.
- Poor performance does not extend the window.
- Mixed performance does not extend the window.
- `insufficient_sample` may remain as a component result after Day 5, but the
  report must identify exactly which component and evidence requirement remain
  insufficient.
- Any future behavior change requires a separate Promotion Framework review.

## Authority

This document controls the current Q9 forward-window operation. Where older
documents say that A/B/C instrumentation is incomplete or that the window is
waiting for implementation, this protocol supersedes those status statements.
The underlying Q9 evaluation contract and full-chain matrix remain unchanged.
