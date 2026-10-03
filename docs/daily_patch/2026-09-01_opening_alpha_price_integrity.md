# 2026-09-01 Opening Alpha Price Integrity

## Incident

- Symbol: `001210` (금호전기)
- Scanner Rank-1 observation: approximately 09:00, 12,950
- Actual entry: 09:02:55, 13,830
- Signal-to-entry drift: +6.80%
- Actual exit: 09:04:12, 13,590
- Broker realized return: -2.62% after mock costs
- Monitor hard-stop mark: 13,130, while the account position mark was 13,530

The Rank-1 hypothesis identified a strong short-horizon move, but the controlled
entry arrived after a material price displacement. The exit then used a stale
quote because the held symbol had fallen outside the Scanner candidate quote
hydration set. This trade is therefore execution-contaminated evidence and must
not be treated as a clean rejection of the Opening Alpha hypothesis.

## Corrections

1. Quote hydration always includes selected and open-position symbols.
2. Market quotes carry an observed timestamp.
3. Stale quotes older than 90 seconds are replaced with an account-position live
   price; if no trustworthy fallback exists, the stale quote is rejected.
4. Exit observability records quote age, divergence, replacement and rejection.
5. Opening Alpha records its first Rank-1 signal price and rejects positive
   signal-to-entry drift above 2%.
6. Immediately before broker submission, Opening Alpha compares that same
   initial signal price with the latest available best ask. Drift above 2% is
   classified as `NOT_SENT` with
   `opening_alpha_execution_price_drift`; the broker order API is not called.
7. For a hard-stop candidate, a market quote older than the expected refresh
   cadence is cross-checked with the account current price. When the two sources
   disagree on the stop outcome, the account/fresh price is authoritative in
   either direction. A stale quote without a valid fallback cannot force exit.
8. Post-exit EOD can reuse the Opening Rank-1 observed close when minute data is
   incomplete.
9. Alpha Board runtime validation is generated from the authoritative runtime
   builder and cannot collapse to an empty object during board canonicalization.
10. The 16:00 Opening Rank-1 closeout refresh retries in local-artifact mode when
   Kiwoom history lookup fails, preserving the closeout bundle while exposing
   `degraded_offline_fallback` and the original network error.

## Recalculated Outcome

Post-exit checkpoints from the actual 13,590 exit:

| Horizon | Price | Return |
|---|---:|---:|
| +5m | 14,080 | +3.61% |
| +15m | 13,990 | +2.94% |
| +30m | 13,740 | +1.10% |
| +60m | 13,110 | -3.53% |
| EOD | 13,070 | -3.83% |

The early stop was too aggressive relative to the trustworthy market path, but
holding blindly to EOD would also have lost money. The valid conclusion is to
fix signal-price and quote freshness integrity, not to globally loosen stops or
enter every Rank-1 candidate.

## Policy Boundary

- Changed: controlled Opening Alpha signal-price integrity and stale-price safety.
- Unchanged: Scanner ranking, Strategist prompts, normal entry gates, normal exit
  thresholds, Q10/Q12 hypotheses and Executor routing.
