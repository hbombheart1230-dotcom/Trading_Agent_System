# Q8 Historical Review: 2026-06-01 to 2026-06-16

Purpose: reuse prior live and shadow evidence without mixing incompatible artifact eras.

This review is evaluation-only. It does not change entry, exit, scanner, Strategist, or execution behavior.

## Data Windows

- Live trade performance: usable from 2026-05-18 onward when truth-surface PnL exists.
- Q8 shadow evaluation: most useful from 2026-05-26 onward when candidate shadow summaries are populated.
- Market regime rail: most useful from 2026-06-02 onward when rail IDs are attached to daily summaries.
- Broker truth reconciliation: strongest from 2026-06-08 onward after post-close order-pair repair.

## Live Trade Summary

- Trade report files: **45**
- Return samples: **45**
- Win rate: **4.44%**
- Average return: **-1.1179%**

| Day | Trades | Closed | Returns | Missing | Win | Avg | Raw | Deduped | Trusted | Gate | Allowed | Rail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-01 | 7 | 7 | 7 | 0 | 0.0% | -1.52% | 1157 | 0 | 0 | legacy/no_gate | False | - |
| 2026-06-02 | 1 | 1 | 1 | 0 | 0.0% | -1.20% | 1474 | 0 | 0 | legacy/no_gate | False | us_tech_risk_on_korea_weak |
| 2026-06-03 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 0 | 0 | 0 | legacy/no_gate | False | - |
| 2026-06-04 | 1 | 1 | 1 | 0 | 0.0% | -1.79% | 1144 | 0 | 0 | legacy/no_gate | False | risk_off_breadth_collapse |
| 2026-06-05 | 2 | 2 | 2 | 0 | 0.0% | -1.14% | 872 | 0 | 0 | legacy/no_gate | False | risk_off_breadth_collapse |
| 2026-06-08 | 12 | 12 | 12 | 0 | 8.3% | -0.88% | 777 | 0 | 0 | legacy/no_gate | False | krx_night_futures_gap_down |
| 2026-06-09 | 7 | 7 | 7 | 0 | 14.3% | -0.65% | 1172 | 0 | 0 | legacy/no_gate | False | krx_night_futures_gap_up |
| 2026-06-10 | 5 | 5 | 5 | 0 | 0.0% | -1.59% | 1090 | 0 | 0 | legacy/no_gate | False | krx_night_futures_gap_down |
| 2026-06-11 | 5 | 5 | 5 | 0 | 0.0% | -0.97% | 911 | 0 | 0 | legacy/no_gate | False | krx_night_futures_gap_down |
| 2026-06-12 | 3 | 2 | 2 | 0 | 0.0% | -1.81% | 860 | 0 | 0 | legacy/no_gate | False | krx_night_futures_gap_up |
| 2026-06-15 | 4 | 4 | 4 | 0 | 0.0% | -1.33% | 949 | 0 | 0 | legacy/no_gate | False | krx_night_futures_gap_up |
| 2026-06-16 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1625 | 788 | 754 | promotion_blocked_no_repeatable_candidate | False | us_tech_risk_on_korea_weak |

## Q8 Promotion Eligibility

- status: `promotion_blocked_by_trust_gate_or_legacy_data`
- trusted gate days: **1**
- promotion allowed days: **0**
- rule: Historical conclusions require daily evaluation_trust_gate.promotion_allowed=true. Legacy daily summaries without trust gate are observation-only.

## Trade Pattern Evidence

### By Tactic

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| defensive_observe | 24 | 4.2% | -1.090% |
| opening_range_breakout | 10 | 10.0% | -0.727% |
| vwap_reclaim_pullback | 9 | 0.0% | -1.462% |
| volume_breakout | 3 | 0.0% | -2.083% |

### By Entry Reason

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| 진입 사유는 hold입니다 | 2 | 0.0% | -1.395% |
| 진입 사유는 VWAP 위 눌림목 구조와 거래량 확인입니다 | 2 | 0.0% | -1.122% |
| 진입은 VWAP 위 눌림목 구조와 거래량 확인 조건에서 실행됐습니다. 052420이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 2 | 0.0% | -0.835% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 스캐너 상위 후보 089030은 breakout not ready 이유로 보류됐고 122630 차순위 재평가 6위 진입으로 전환됐습니다. 실제 트리거는 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파였습니다 | 1 | 100.0% | 6.480% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 스캐너 상위 후보 035420은 below vwap reclaim not ready 이유로 보류됐고 034220 차순위 재평가 4위 진입으로 전환됐습니다. 실제 트리거는 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파였습니다 | 1 | 0.0% | -4.630% |
| 진입은 VWAP 위 눌림목 구조와 거래량 확인 조건에서 실행됐습니다. 스캐너 상위 후보 291810은 too extended from vwap 이유로 보류됐고 017900 차순위 재평가 7위 진입으로 전환됐습니다. 실제 트리거는 VWAP 위 눌림목 구조와 거래량 확인이었습니다 | 1 | 0.0% | -2.940% |
| 진입은 VWAP 위 눌림목 구조와 거래량 확인 조건에서 실행됐습니다. 스캐너 상위 후보 095610은 too extended from vwap 이유로 보류됐고 291810 차순위 재평가 2위 진입으로 전환됐습니다. 실제 트리거는 VWAP 위 눌림목 구조와 거래량 확인이었습니다 | 1 | 0.0% | -2.370% |
| 진입은 눌림목 rebound above vwap with confirmation 조건에서 실행됐습니다. 089030이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 1 | 0.0% | -1.960% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 089030이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 1 | 0.0% | -1.910% |
| 진입은 hold 조건에서 실행됐습니다. 스캐너 상위 후보 240810은 too extended from vwap 이유로 보류됐고 093370 차순위 재평가 2위 진입으로 전환됐습니다. 실제 트리거는 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파였습니다 | 1 | 0.0% | -1.910% |

### By Exit Reason

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| 추세 훼손 | 19 | 0.0% | -0.895% |
| 고정 손절 기준 | 16 | 0.0% | -2.056% |
| VWAP 이탈 | 4 | 25.0% | -0.875% |
| 거래량 둔화 익절 | 1 | 100.0% | 6.480% |
| 장마감 정리 기준 | 1 | 0.0% | -0.600% |
| Executor recorded SELL, but the monitor had not confirmed the exit yet (hold). This is a monitor/executor mismatch, n | 1 | 0.0% | 0.000% |

## Q8 Shadow Summary

- Q8 shadow summary days: **12**
- Q8 blocker forward-review days: **10**

### Top Shadow Reasons

| Reason | Count |
| --- | --- |
| below_vwap_reclaim_not_ready | 3956 |
| pullback_not_mature | 1621 |
| breakout_not_ready | 1569 |
| volume_insufficient | 985 |
| volume_confirmation_missing | 970 |
| too_extended_from_vwap | 506 |
| pullback_below_vwap_reclaim_not_ready | 367 |
| human_chart_sanity_guard_blocked | 357 |
| quant_entry_block:cost_edge_fail | 290 |
| breakout_above_recent_high_with_vwap_hold_and_volume_confirmation | 194 |
| minute_candle_missing | 167 |
| breakout_above_recent_high_with_vwap_structure_confirmation | 158 |
| breakout_continuation_structure_guard_blocked | 68 |
| pullback_structure_above_vwap_with_volume_confirmation | 65 |
| quant_entry_block:vwap_pullback_promoted_quality_gate | 47 |

### Forward Blocker Review

| Reason | n | obs | Latest | MFE | MAE | Missed | Adverse | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| below_vwap_reclaim_not_ready | 1971 | 1845 | 0.0937% | 1.2706% | -1.1348% | 41.8% | 61.5% | retain_under_observation |
| breakout_not_ready | 934 | 886 | 0.0640% | 1.1225% | -1.0916% | 35.9% | 58.6% | adjust_and_retest |
| pullback_not_mature | 607 | 580 | 0.0093% | 0.8075% | -0.7590% | 29.7% | 52.9% | retain_under_observation |
| volume_confirmation_missing | 357 | 329 | -0.1590% | 1.4414% | -1.6008% | 41.9% | 73.2% | retain_under_observation |
| human_chart_sanity_guard_blocked | 206 | 194 | -0.4278% | 1.1904% | -2.0643% | 38.1% | 75.8% | promotion_review_target |

## Below-VWAP Reclaim Subtype Review

- Subtype count days: **12**
- Subtype forward days: **7**
- Note: subtype forward evidence is available only after the entry-lane observation fields were added.

### Subtype Counts

| Subtype | Count |
| --- | --- |
| true_below_vwap_failure | 2467 |
| near_vwap_reclaim_setup | 337 |
| reclaim_in_progress_with_improving_volume | 88 |
| post_reclaim_pullback_candidate | 7 |

### Subtype V2 Counts

| Subtype V2 | Count |
| --- | --- |
| deep_below_vwap_failure | 892 |
| ordinary_below_vwap_failure | 806 |
| shallow_below_vwap_rebound | 345 |
| near_vwap_reclaim_setup | 142 |
| confirmed_post_reclaim_pullback | 6 |

### Subtype Forward Outcomes

| Subtype | n | obs | 3m | 5m | 15m | 30m | 60m | MFE5 | MAE5 | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vwap_reclaim:true_below_vwap_failure | 2002 | 1864 | 0.0323% | 0.0568% | 0.0473% | 0.1336% | 0.3292% | 0.5353% | -0.4589% | review_classifier_or_label |
| vwap_reclaim:near_vwap_reclaim_setup | 287 | 278 | -0.0049% | 0.0433% | -0.0434% | -0.1889% | -0.2638% | 0.3811% | -0.3668% | retain_under_observation |
| vwap_reclaim:reclaim_in_progress_with_improving_volume | 58 | 53 | 0.0500% | -0.0119% | -0.1282% | -0.2949% | 0.0941% | 0.3507% | -0.3178% | keep_blocked |

## Recommendations

| Candidate | Decision | Evidence |
| --- | --- | --- |
| all_q8_candidates | retain_under_observation | no historical day passed the Q8 evaluation trust gate |

## Operator Conclusion

- Prior data is useful, but it must be sliced by artifact era.
- Live trade PnL already shows persistent negative expectancy in stop/trend-break/low-break exits.
- Q8 shadow raw sample size alone is not promotion evidence.
- Promotion review requires trusted same-day forward outcomes, canonical dedupe, and evaluation_trust_gate.promotion_allowed=true.
- Historical reports generated before the trust gate are legacy observation material, not policy-promotion evidence.
