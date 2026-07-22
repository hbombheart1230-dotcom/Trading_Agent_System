# Q16 Cost-Horizon Fit Patch - 2026-07-21

## Cost Basis Correction

The original Q16 evidence table used the Kiwoom mock-account observed cost as
its only net-return basis. That basis remains valid for mock-account PnL, but it
must not be treated as the only estimate of live deployment economics.

Evaluation now reports two independent views:

| Basis | Round-trip cost | With 0.05% slippage | Use |
| --- | ---: | ---: | --- |
| Mock observed | approximately 1.0368% | approximately 1.0868% | mock broker PnL/cash truth |
| Live KRX equity assumption | 0.2300% | 0.2800% | real-account strategy evaluation |

The live assumption consists of Kiwoom OpenAPI fees of 0.015% per side and the
2026 KRX equity sell tax of 0.20%. ETF/ETN tax treatment must be classified by
instrument and is not inferred from the equity assumption.

This is an evaluation/observability correction. It does not change runtime
entry, exit, order, or broker-accounting behavior. Q16 must inspect both net
views before its final RETAIN/ROLL_BACK decision.

## Decision

`APPLY_ONE_BEHAVIOR_PATCH`

Q15 is closed as `RETAIN`. Q16 changes one Monitor cost-edge default and leaves
Scanner ranking, Strategist, Commander, entry signals, exits, and execution
unchanged.

## Evidence

The 2026-07-13 through 2026-07-21 full-chain review contains six observed days
and more than 1,400 Top1 forward observations.

| Horizon | Top1 Gross Avg | Top1 Net Avg | Top3 Net Avg | Top5 Net Avg | Top10 Net Avg |
| --- | ---: | ---: | ---: | ---: | ---: |
| +5m | +0.0282% | -1.0586% | -1.1093% | -1.1128% | -1.1177% |
| +15m | +0.0920% | -0.9948% | -1.0701% | -1.0869% | -1.1013% |
| +30m | +0.1637% | -0.9231% | -1.0789% | -1.0741% | -1.1099% |
| EOD | +0.9166% | -0.1702% | -0.7842% | -0.7597% | -0.6293% |

Top1 consistently outperforms broader TopK averages. The evidence therefore
does not support changing Scanner score weights. The failure is absolute
cost-adjusted intraday edge, not relative ordering.

The 2026-07-21 006800 entry illustrates the calibration defect:

- directional edge evidence: unavailable
- volatility proxy: 5.4272%
- proxy haircut: 0.35
- estimated gross edge: 1.8995%
- required gross edge: 1.65%
- result: passed
- observed aggregate Top1 +30m gross average: 0.1637%

ATR and volatility describe possible movement size, not direction. Treating
them as sufficient directional return evidence materially overstates edge.

## Patch

Change the default:

```text
allow_triggered_signal_proxy_edge: true -> false
```

Effect:

- A triggered entry signal no longer disables the directional-edge requirement.
- ATR or volatility alone cannot satisfy cost-edge by default.
- Explicit directional expected-move evidence remains eligible.
- An explicit policy override can still enable proxy behavior for a separately
  controlled strategy, but no such production override is added here.
- Q10, Q11, Q12, order execution, and exit behavior are unchanged.

## Validation Contract

Use frozen Q13/Q14 plus the existing full-chain component review.

- Start: next full trading day after 2026-07-21
- Maximum duration: 3 full trading days
- Directional minimum: 20 rejected proxy-only candidates with completed +15m
  and +30m observations across at least 2 days
- Do not extend beyond 3 days. Close as `RETAIN`, `ROLL_BACK`, or
  `INSUFFICIENT_EVIDENCE`.

Primary checks:

- proxy-only cost-filter rejection count
- directional-edge-backed candidate count
- realized trade count
- +15m/+30m cost-net expectancy of admitted candidates
- missed opportunities among rejected proxy-only candidates

Do not add another behavior patch during this comparison. A low trade count by
itself is not a rollback reason. Roll back only if rejected proxy-only candidates
show repeatable cost-net positive outcomes while admitted directional candidates
do not improve quality.

Decision rules:

- `RETAIN`: rejected proxy-only candidates remain non-positive after cost at
  +15m and +30m, or directional-evidence candidates show a material quality
  improvement without loss regression.
- `ROLL_BACK`: rejected proxy-only candidates are cost-net positive with profit
  factor above 1.0 at +30m on at least 2 days.
- `INSUFFICIENT_EVIDENCE`: the directional minimum is not reached by the end of
  day 3. Close the window without silently extending it.
