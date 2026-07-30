# Q16 Close Decision - 2026-07-24

## Decision

`RETAIN`

Q16 is closed. Do not extend its validation window.

## Evidence

| Day | Exact Rejections | +30m Observed | Live Net Avg | Profit Factor | Positive Day |
| --- | ---: | ---: | ---: | ---: | --- |
| 2026-07-23 | 47 | 43 | +0.6919% | 2.6767 | yes |
| 2026-07-24 | 45 | 45 | -0.7395% | 0.0830 | no |
| Cumulative | 92 | 88 | -0.0401% | 0.9347 | 1 of 2 |

The fixed rollback rule required positive +30m live-net expectancy and profit
factor above 1.0 on both minimum evidence days. That condition was not met.

## Interpretation

- ATR and volatility remain magnitude proxies, not directional return evidence.
- `allow_triggered_signal_proxy_edge` remains disabled by default.
- Low trade count alone does not authorize rollback.
- The 2026-07-24 sample was concentrated in `003030`: 45 rows represented 11
  distinct baseline minutes. The decision satisfies the fixed contract but is
  not treated as 45 independent trades.

## Follow-Up Boundary

Q16 exposed a separate contract gap: no runtime component supplied explicit,
horizon-matched directional expectancy to the Monitor cost filter. That gap is
handled by Q17 without reopening Q16.
