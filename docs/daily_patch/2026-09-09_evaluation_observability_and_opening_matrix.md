# 2026-09-09 Evaluation Observability and Opening Matrix

## Scope

- Observability and reporting corrections only.
- No Scanner, Strategist, Commander, Monitor, order, or broker policy change.

## Corrections

- A realized losing day with only one sample is now `YELLOW`, never `GREEN`.
- Q12 input expiry after the fixed 09:12 opening window is reported as
  `WINDOW_CLOSED`; a stale input during the active window remains `INPUT_DELAY`.
- Q10 index captures without source-time/final-close verification remain excluded
  from scoring, but their captured values and provenance are shown separately.
- Q9 validity now exposes forward outcome reason and checkpoint-status signature
  counts. The 95% coverage requirement is unchanged.

## Opening Alpha Comparison

The new `opening_policy_matrix` compares the first Opening Alpha episode per
day-symbol within each discriminator cell across:

- common stock versus ETF,
- active relaxation lane (`HIGH_COMMON_DIRECTIONAL` or `CONFIRMED_RECURRENT_RANK`),
- risk band,
- liquidity-only versus directional and other setup classes,
- scalp versus intraday and missing horizon evidence,
- +5m, +15m, +30m, +60m, and EOD net outcomes.

This matrix is observation-only and cannot authorize a behavior change.
Every future controlled-probe decision also persists the same stable discriminator
cell ID through its evaluation and submission ledgers.

## Full Regression Alignment

The first full regression run found four failures. They were test and metadata
drift, not new runtime behavior defects:

- Two `decide_trade` tests still expected `max_hold_sec` to force a SELL at the
  time limit. Since the 2026-05-13 policy, an enabled cost-aware profit floor
  turns max-hold/time-stop into a reassessment point and may retain the position
  when the executable return has not cleared costs. The fixtures now disable
  that floor explicitly when testing the legacy unconditional max-hold branch.
- One cooldown test still treated `SELL_COOLDOWN` as runtime authority. Current
  authority is `applied_policy.execution.cooldowns.sell_sec`; the test now uses
  that contract and isolates the broker cost profile.
- Patch-note metadata declared 68 entries while the document contained 69. The
  declared count was corrected without changing any patch-note history.

Verification after alignment:

- Focused regression: `4 passed`.
- Full regression: `3053 passed, 1 skipped, 0 failed`.
- Production runtime was stopped during the full run, so external runtime writes
  could not contaminate pytest isolation verification.
- No trading, eligibility, exit, broker, or guard behavior was changed by this
  regression alignment.

## Artifacts

- `reports/evaluation/short_alpha_discriminator/YYYY-MM-DD/opening_policy_matrix.json`
- `reports/evaluation/short_alpha_discriminator/YYYY-MM-DD/opening_policy_matrix.md`
- `reports/evaluation/daily/YYYY-MM-DD/q9_day_validity.json`
- `reports/evaluation/baseline_samsung_hynix/YYYY-MM-DD/q10_forward_validation/q10_forward_validation_report.md`
