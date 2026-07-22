# Post-Q15 Adjustment Retest Close - 2026-07-21

## Decision

`RETAIN`

The fixed two-full-trading-day retest is closed. Do not extend this window.

Retain the narrow Q15 adjustment that removed `volume_insufficient` only from
the anticipated runner-up pre-veto. Monitor's current-data volume hard gate
remains unchanged.

## Evidence Window

- Full trading days: 2026-07-20 and 2026-07-21
- Q9 validity on 2026-07-21: `VALID`
- Complete P/A/B/C windows on 2026-07-21: 596
- Q8 trusted forward coverage on 2026-07-21: 92.31%
- Runner-up cascade attempts on 2026-07-21: 201
- Actual runner-up fallback executions on 2026-07-21: 0

The adjustment allowed anticipated candidates to reach current Monitor review.
It did not bypass Monitor and did not create an attributable realized loss.

On 2026-07-21, `volume_confirmation_missing` shadow candidates had an average
latest gross move of +0.3895%. This did not exceed the approximately 1.0868%
round-trip cost and slippage assumption. The evidence therefore supports
retaining Monitor's hard volume confirmation gate, not relaxing it.

## 2026-07-21 Defect Exclusion

The realized 006800 loss is not evidence against Q15, Strategist selection, or
the entry rule.

- Broker truth: -27,411 KRW, -0.92%
- Hold time: 34 seconds
- Cause: an invalid scanner/engine VWAP fallback was interpreted as session VWAP
  and triggered a false `trend_breakdown` exit
- Post-exit path: +15m +1.53%, +30m +0.98%, +60m +0.71%, EOD +2.50%
- Maximum post-exit upside: +4.01%

The VWAP fallback defect was fixed and regression-tested on 2026-07-21. This
trade remains in broker and artifact truth, but must be excluded from strategy,
selection, and entry-effect promotion evidence. It is an exit-data defect case.

Current Q13/Q14 labels such as `ENTRY_TOO_EARLY`, `Strategist Override`, and
`Exit Horizon` describe the observed artifact chain but must not be used as a
behavior conclusion for this trade because the realized outcome was dominated
by the confirmed exit defect.

## Integrity Repairs

The close review also fixed duplicate closed-trade synthesis. An authoritative
broker order pair is now registered before reconciliation skips an already
authoritative lifecycle. The duplicate synthetic 006800 bundle was removed,
leaving one broker-backed trade bundle.

Verification:

- closeout maintenance: success
- account snapshot API calls: 19 / 19 successful
- residual positions: 0
- post-exit observations: 1 / 1, including EOD
- reconciler regression tests: 13 passed
- monitor exit regression tests: 112 passed

## Next Step

Q15 is frozen as retained. Do not apply another runner-up or volume relaxation.

The next behavior candidate remains `Scanner Ranking Failure`, but no scanner
ranking patch is authorized by today's realized trade. First produce a bounded
pre-patch review from existing cost-net Top1/Top3/Top5/Top10 and score-component
evidence. Select at most one ranking component only if that review identifies a
repeatable defect. Continue using frozen Q13/Q14 metrics for the before/after
comparison.
