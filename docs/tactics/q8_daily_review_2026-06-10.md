# Q8 Daily Review: 2026-06-10

Purpose: record the end-of-day Q8 evidence review for 2026-06-10, including
the five closed losses, the risk-off market rail, the repeated-blocker entry
expansion defect, and the follow-up patch that makes this case a permanent
validation baseline.

This review documents the evidence and the policy decision. The runtime patch
was applied separately in commit `c84eb7c`.

## Source Artifacts

- Daily summary: `reports/operator_summary/daily/2026-06-10/daily_summary.json`
- Daily summary markdown: `reports/operator_summary/daily/2026-06-10/daily_summary.md`
- Market rail review: `reports/operator_summary/daily/2026-06-10/market_regime_rail_review.json`
- Trade reports:
  - `reports/trades/2026-06-10/1000/TRD_20260610_052420_01/`
  - `reports/trades/2026-06-10/1000/TRD_20260610_089030_01/`
  - `reports/trades/2026-06-10/1000/TRD_20260610_089030_02/`
  - `reports/trades/2026-06-10/1100/TRD_20260610_093370_01/`
  - `reports/trades/2026-06-10/1400/TRD_20260610_052420_02/`
- Quant shadow candidates: `data/logs/quant_shadow_candidates/2026-06-10/`

## Runtime And Trade Summary

| Field | Value |
| --- | ---: |
| Live trades | 5 |
| Closed trades | 5 |
| Win / loss / flat | 0 / 5 / 0 |
| Win rate | 0.00% |
| Average return | -1.594% |
| Average hold time | 1253.6 sec |
| Return basis | truth_surface_net |
| Residual positions | 0 |

Trade outcomes:

| Trade | Symbol | Result | Entry context | Commander entry control | Exit |
| --- | --- | ---: | --- | --- | --- |
| `TRD_20260610_052420_01` | `052420` | -1.35% | pullback rebound above VWAP with volume confirmation | `expand_candidate_pool` | VWAP breakdown |
| `TRD_20260610_089030_01` | `089030` | -1.85% | volume insufficient | `expand_candidate_pool` | stop loss |
| `TRD_20260610_089030_02` | `089030` | -2.01% | pullback structure above VWAP with volume confirmation | `expand_candidate_pool` | stop loss |
| `TRD_20260610_093370_01` | `093370` | -1.75% | volume insufficient | `defensive_top3_candidate_cascade` | stop loss |
| `TRD_20260610_052420_02` | `052420` | -1.27% | below VWAP reclaim not ready | `defensive_top3_candidate_cascade` | trend breakdown |

## Market Regime

The day was a high-confidence risk-off / gap-down rail.

| Input | Value |
| --- | ---: |
| rail_id | `krx_night_futures_gap_down` |
| rail_confidence | high |
| KOSPI | -5.35% |
| KOSDAQ | -2.33% |
| KOSPI200 | -5.88% |
| KRX night futures | -4.03% |
| Breadth | -0.539 |

Expected behavior under this rail:

- Treat the session as broad gap-down risk.
- Require confirmed relative strength before entry.
- Keep cost-edge and volume confirmation strict.
- Do not expand candidate scope just because the top candidate is repeatedly
  blocked.

## Root Cause

The losses were not caused by missing cost-floor enforcement.

All five live trades were later summarized as cost-floor met. The failure was
in the entry-scope control layer:

1. `below_vwap_reclaim_not_ready` repeated more than 30 times.
2. Commander interpreted the repeated blocker as a reason to widen the candidate
   pool.
3. In non-supportive market conditions, the prior code still allowed
   `defensive_top3_candidate_cascade`.
4. The result was live entry into rank2/rank3 or weak readiness states while the
   market rail was risk-off.

The critical bad behavior:

```text
risk-off or defensive context
+ repeated expandable blocker
+ remaining position capacity
=> candidate pool expansion / top3 cascade
```

This behavior is rejected.

## Artifact Integrity Finding

The trade lifecycle bundles did not consistently preserve the actual entry-time
quant surfaces:

- `entry_quant_decision` was missing or `{}` in exit-context surfaces.
- `quant_entry_enforcement` was not present in the lifecycle bundle.
- `market_rail_translation` was not present in the lifecycle bundle.
- `risk_off_defensive_observe_policy` was not present in the lifecycle bundle.

The daily summary reconstructed some quant fields from fallback sources. That is
useful for reporting, but it is not a substitute for preserving the actual
entry-time decision surface.

Patch requirement:

- Persist entry-time quant decision, enforcement, market rail translation, and
  risk-off defensive policy in order metadata / monitor output.

## Q8 Shadow Evidence

| Field | Value |
| --- | ---: |
| Raw candidates | 1090 |
| Deduped candidates | 580 |
| Evaluated candidates | 1071 |
| Forward outcome coverage | 92.4% |
| Would-enter candidates | 10 |
| Guard-blocked candidates | 90 |
| Opening probe would-enter | 0 |
| Largecap surge would-enter | 0 |

Selected blocker forward review:

| Blocker | Candidates | Observed | Avg latest | MFE | Adverse rate | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `breakout_not_ready` | 52 | 48 | -0.3025% | 0.5982% | 54.17% | adjust and retest |
| `pullback_not_mature` | 25 | 22 | -0.7354% | 0.5295% | 90.91% | adjust and retest |
| `human_chart_sanity_guard_blocked` | 17 | 17 | -0.3042% | 1.2916% | 76.47% | promotion review target |
| `volume_confirmation_missing` | 47 | 43 | 1.4984% | 4.0226% | 72.09% | retain under observation |
| `below_vwap_reclaim_not_ready` | 284 | 264 | -0.1043% | 0.9348% | 65.91% | retain under observation |

Interpretation:

- `below_vwap_reclaim_not_ready` remains too noisy to use as a relaxation
  trigger in risk-off.
- `pullback_not_mature` should remain blocked; adverse rate was very high.
- `volume_confirmation_missing` has missed-opportunity evidence, but also high
  adverse rate. It needs subtype separation, not broad relaxation.
- No realized-trade evidence supports widening the candidate pool under
  risk-off conditions.

## Strategist And Lane Evaluation

Daily strategist evaluation:

- Primary tactic: `defensive_observe`
- Primary lane: `defensive`
- Lane selection quality: `poor_lane_selection`
- Overused lane/tactic: `defensive_observe`
- Underused shadow lane: `breakout`

Realized tactic outcomes:

| Tactic | Count | Win rate | Avg return |
| --- | ---: | ---: | ---: |
| `defensive_observe` | 4 | 0.0% | -1.5025% |
| `vwap_reclaim_pullback` | 1 | 0.0% | -1.9600% |

Interpretation:

- `defensive_observe` acted as an entry-expansion path, not as a defensive
  observe/no-trade stance.
- In a high-confidence risk-off rail, this is the wrong behavior.
- `defensive_observe` must be treated as observation/no-entry unless an explicit
  risk-off exception is recorded and all exception conditions are satisfied.

## Policy Decision

Outcome: `ADJUST AND RE-TEST`

Promoted guardrail:

- In `risk_off` or `defensive` mode, repeated blockers must not expand the
  candidate pool.
- Candidate rank scope must be clamped to rank1.
- Runner-up cascade must be disabled.
- Scanner aggression and diversification expansion must be zeroed.

Rejected behavior:

- `defensive_top3_candidate_cascade` under risk-off.
- `expand_candidate_pool` under risk-off.
- Treating repeated `below_vwap_reclaim_not_ready` as a reason to relax entry.

Artifact requirement:

- Future trades must persist:
  - `entry_quant_decision`
  - `quant_entry_enforcement`
  - `market_rail_translation`
  - `risk_off_defensive_observe_policy`

## Patch Applied

Commit: `c84eb7c Stabilize Q8 tactics and risk-off controls`

Implemented changes:

- `graphs/commander_runtime.py`
  - risk-off / defensive repeated blockers now produce
    `risk_off_no_entry_expansion`.
  - `max_priority_rank=1`, `max_runner_ups=0`, `cascade_enabled=false`.
  - scanner `scan_aggressiveness=0` and `diversification_bias=0` under this
    mode.
- `libs/runtime/strategist_input_quality.py`
  - `krx_night_futures_gap_down`, `gap_down`, and `breadth_collapse` now
    activate risk-off exception policy.
- `graphs/nodes/monitor_node.py`
  - order metadata and monitor output now include entry-time quant enforcement,
    market rail translation, and risk-off defensive policy.

Validation:

- `tests/test_monitor_feedback_adaptive_policy.py`
- `tests/test_strategist_input_quality_risk_off.py`
- `tests/test_trade_symbol_context.py`
- `tests/test_market_rail_translation.py`
- `tests/test_operator_summary_broker_day_reconciliation.py`

Result: 17 tests passed.

## Next Session Validation Checklist

On the next live session, verify:

1. When rail is `krx_night_futures_gap_down` or risk-off, `entry_control.mode`
   becomes `risk_off_no_entry_expansion` when repeated blockers appear.
2. `defensive_top3_candidate_cascade` does not appear under risk-off.
3. `expand_candidate_pool` does not appear under risk-off.
4. Scanner policy shows:
   - `max_priority_rank=1`
   - `max_runner_ups=0`
   - `scan_aggressiveness=0`
   - `diversification_bias=0`
5. Trade lifecycle/report artifacts preserve:
   - `entry_quant_decision`
   - `quant_entry_enforcement`
   - `market_rail_translation`
   - `risk_off_defensive_observe_policy`
6. If trades still occur under risk-off, each trade must show an explicit
   risk-off exception path and all exception conditions must be auditable.

## Promotion Framework Status

This review does not promote a new profit-seeking tactic.

It promotes a defensive safety rule:

```text
Risk-off repeated blockers are evidence to remain selective,
not evidence to widen the candidate pool.
```

Future review should evaluate whether this reduces loss frequency without
creating unacceptable missed opportunity cost.
