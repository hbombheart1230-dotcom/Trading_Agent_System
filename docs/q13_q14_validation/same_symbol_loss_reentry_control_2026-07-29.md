# Same-Symbol Loss Reentry Control - 2026-07-29

## Decision

`APPLY_ONE_BEHAVIOR_PATCH`

After a full loss exit, the same symbol is not eligible for another entry
during the same Korean trading day. Other symbols remain eligible.

The control does not apply after:

- a profitable or flat exit
- a partial exit
- an exit whose PnL is unavailable
- a loss from a prior trading day

## Evidence

The existing Q14 trusted ledger found:

| Cohort | Count | Win Rate | Average Return |
| --- | ---: | ---: | ---: |
| First entry | 72 | 13.89% | -0.8506% |
| Same-day repeat entry | 27 | 3.70% | -1.2478% |
| Repeat after a loss | 24 | 4.17% | -1.2756% |
| Repeat after a non-loss | 3 | 0.00% | -1.0252% |

The repeat-after-loss cohort had one winner and a profit factor of 0.0029.

An independent Kiwoom fill-order reconstruction found:

| Cohort | Count | Win Rate | Average Return |
| --- | ---: | ---: | ---: |
| First round trip | 79 | 17.72% | -0.7360% |
| All repeat round trips | 38 | 7.89% | -0.9282% |
| Repeat after a loss | 32 | 6.25% | -1.1404% |
| Repeat after a win | 6 | 16.67% | +0.2037% |

Historical snapshot duplication and malformed negative intervals were treated
as integrity warnings, not as the sole authorization source. The trusted Q14
ledger independently reaches the same conclusion.

## Scope

This is not a permanent symbol penalty and does not change Scanner weights.
It is a transient per-symbol execution state:

```text
full SELL
  -> realized return is negative
  -> persist symbol/day/loss outcome
  -> Monitor hard-blocks only that symbol for the rest of the day
```

The state is keyed by symbol, so another position opening or closing cannot
erase the prior loss record.

## Observability

Monitor entry artifacts include:

- `same_symbol_loss_reentry_control.evaluated`
- `same_symbol_loss_reentry_control.blocked`
- `same_symbol_loss_reentry_control.prior_exit`
- guard reason `same_symbol_loss_reentry_blocked`

Unknown PnL fails open and remains visible as `UNKNOWN`; it is never inferred
as a loss.
