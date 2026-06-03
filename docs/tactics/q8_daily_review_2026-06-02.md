# Q8 Daily Review: 2026-06-02

Purpose: record the end-of-day Q8 evidence review for 2026-06-02 and separate
artifact integrity fixes from tactic promotion decisions.

This review is documentation only. It does not change runtime behavior, entry
logic, exit logic, scanner ranking, monitor guards, Strategist prompts, or
execution.

## Source Artifacts

- Daily report: `reports/operator_summary/daily/2026-06-02/daily_report.json`
- Daily summary: `reports/operator_summary/daily/2026-06-02/daily_summary.json`
- Broker reconciliation:
  `reports/reconciliation/broker_trade_reconciliation_2026-06-02.json`
- Account snapshot:
  `data/logs/kiwoom_account_snapshots/2026-06-02/latest.json`
- Quant shadow candidates:
  `data/logs/quant_shadow_candidates/2026-06-02/`

## Runtime And Trade Summary

| Field | Value |
| --- | ---: |
| Source runs | 622 |
| Events | 17,650 |
| Approvals | 3 |
| Blocks | 242 |
| Executions | 3 |
| Execution ok / fail | 2 / 1 |
| Live trades | 1 |
| Closed trades | 1 |
| Average return | -1.20% |
| Average hold | 156 sec |

Closed trade:

| Trade | Symbol | Status | Tactic | Suitability | Entry Cost Floor | Result |
| --- | --- | --- | --- | --- | --- | ---: |
| `TRD_20260602_061040_01` | `061040` | closed | `defensive_observe` | watch | met | -1.20% |

Interpretation:

- Realized closed-trade sample is too small for strategy promotion.
- The live loss is useful as a trade-quality sample, but it is not enough to
  validate or reject `defensive_observe`.
- Q8 should use today's shadow dataset for pre-entry guard and missed
  opportunity review, while keeping realized-PnL claims on hold.

## Artifact Integrity Result

Status after repair: `PASS`.

Verified fields:

| Surface | Result |
| --- | --- |
| Broker order/fill count | local 2, broker 2, matched by order number 2 |
| Broker missing rows | 0 local-only, 0 broker-only |
| Broker account position | 0 residual positions |
| `ka10170` day trade diary | 1 row, closed symbol `061040` |
| Trade report integrity | expected 1, checked 1, missing 0 |
| Broker-closed/report-open mismatch | 0 after repair |

Critical defect observed before repair:

- Broker truth showed `061040` fully sold.
- Lifecycle/report truth initially remained open.
- This is an artifact integrity defect, not a tactic-performance conclusion.

Patch status:

- `ka10170` day trade diary rows are now normalized into broker alignment.
- Daily report integrity now exposes `broker_closed_report_open_count`.
- If broker truth says closed but report/lifecycle remains open, daily report
  status becomes `broker_lifecycle_mismatch`.

Promotion impact:

- No Q8 behavior promotion should be based on samples from a day with unresolved
  broker/lifecycle/report conflict.
- After repair, 2026-06-02 is usable for Q8 observation, but the realized trade
  sample remains too small for strategy-level conclusions.

## Q8 Shadow Dataset

| Field | Value |
| --- | ---: |
| Payloads | 594 |
| Candidates | 1,474 |
| Evaluated candidates | 1,454 |
| Evaluated ratio | 98.6% |
| Forward baseline available | 1,375 / 1,474 |
| Forward baseline coverage | 93.3% |
| Forward outcome available | 1,333 / 1,474 |
| Forward outcome coverage | 90.4% |
| Would-enter candidates | 2 |
| Guard-blocked candidates | 161 |
| Actionable guard-blocked candidates | 161 |
| Opening momentum would-enter | 0 |
| Opening largecap surge would-enter | 0 |

Q8 readiness:

- Shadow readiness: `ready`.
- Promotion candidate surfaced by summary: `cost_edge`.
- Summary action: `already_promoted_monitor_hard_gate`.
- Promotion scope: pre-entry filter.

Interpretation:

- Cost-edge remains active and already promoted. Do not re-promote it.
- Live-trade readiness remains `hold_sample_insufficient`.
- Shadow readiness is enough for pre-entry guard review, not for realized
  win-rate claims.

## Top Shadow Reasons

| Reason | Count | Review Status |
| --- | ---: | --- |
| `below_vwap_reclaim_not_ready` | 678 | retain under observation |
| `volume_confirmation_missing` | 147 | retain under observation |
| `pullback_not_mature` | 146 | adjust-and-retest candidate |
| `minute_candle_missing` | 100 | artifact/data availability watch |
| `breakout_not_ready` | 86 | adjust-and-retest candidate |
| `breakout_above_recent_high_with_vwap_structure_confirmation` | 73 | missed-opportunity review target |
| `human_chart_sanity_guard_blocked` | 66 | promotion review target |
| `breakout_above_recent_high_with_vwap_hold_and_volume_confirmation` | 56 | missed-opportunity review target |

## Entry Shape Diagnostics

| Shape | Count |
| --- | ---: |
| `vwap_reclaim` | 678 |
| `breakout` | 215 |
| `pullback` | 199 |
| `volume_confirmation` | 161 |
| `other` | 155 |
| `human_chart_sanity` | 66 |

Additional diagnostics:

- Pullback or VWAP blocked count: 877.
- Breakout-ready-like count: 129.
- Breakout-not-ready count: 213.
- Strategist shadow contrast shows underused shadow lane: `breakout`.

Interpretation:

- The system is still heavily observing/blocking VWAP-reclaim and pullback
  shapes.
- Breakout-like opportunities are visible in shadow but not yet promoted into
  behavior.
- Human chart sanity blocked 66 candidates and needs targeted review before it
  becomes a hard veto or is relaxed.

## Promotion Decisions

| Candidate | Decision | Reason |
| --- | --- | --- |
| Cost floor / cost edge hard gate | retain official policy | Q8 shadow ready and already active; no duplicate promotion needed |
| VWAP pullback quality gate | retain official policy | current baseline says promoted; continue forward-labeled shadow monitoring |
| Volume confirmation missing | retain under observation | high count, but not enough evidence today to relax |
| Pullback maturity | adjust and re-test | count 146; may be too conservative in specific regimes |
| Breakout readiness | adjust and re-test | breakout lane appears underused in shadow diagnostics |
| Human chart sanity guard | promotion review target | 66 blocked candidates; needs blocked-winner and false-positive analysis |
| Opening momentum probe | retain under observation | 0 would-probe today |
| Opening largecap surge | retain under observation | 0 would-probe today |
| Market regime rail | retain observation-only | not yet attached to Q8 evidence as a measured rail |
| Long-horizon unlock | retain under observation | no post-exit evidence sufficient for behavior change |

## Next Review Targets

Because 2026-06-03 is a market holiday, the next live validation day should
focus on:

1. Confirm that `broker_closed_report_open_count` remains 0 after close.
2. Confirm that every closed trade has `ka10170` or fallback broker PnL truth.
3. Review `breakout_not_ready` forward outcomes by symbol and regime.
4. Review `human_chart_sanity_guard_blocked` forward outcomes.
5. Separate `volume_confirmation_missing` correct blocks from missed winners.
6. Attach market regime rail evidence as observation-only before using it for
   strategy feedback.
7. Keep cost-edge and VWAP pullback quality gates active, but monitor missed
   opportunity cost.

## Boundary

Do not promote new behavior from this single day.

Allowed next actions:

- improve artifact integrity reporting
- improve Q8 review summaries
- design market regime rail observation fields
- prepare Trade Evaluator read models

Blocked next actions until more evidence:

- relaxing breakout readiness live behavior
- relaxing human chart guard live behavior
- enabling long-horizon behavior
- changing Strategist prompts based only on this day
- changing scanner ranking based only on this day
