# Q8 Historical Review: 2026-06-01 to 2026-08-21

Purpose: reuse prior live and shadow evidence without mixing incompatible artifact eras.

This review is evaluation-only. It does not change entry, exit, scanner, Strategist, or execution behavior.

## Data Windows

- Live trade performance: usable from 2026-05-18 onward when truth-surface PnL exists.
- Q8 shadow evaluation: most useful from 2026-05-26 onward when candidate shadow summaries are populated.
- Market regime rail: most useful from 2026-06-02 onward when rail IDs are attached to daily summaries.
- Broker truth reconciliation: strongest from 2026-06-08 onward after post-close order-pair repair.

## Live Trade Summary

- Trade report files: **87**
- Return samples: **87**
- Win rate: **11.49%**
- Average return: **-0.8669%**

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
| 2026-06-17 | 1 | 1 | 1 | 0 | 0.0% | -0.85% | 482 | 293 | 272 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-06-18 | 3 | 3 | 3 | 0 | 66.7% | 1.59% | 1067 | 477 | 442 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-06-19 | 1 | 1 | 1 | 0 | 0.0% | -0.83% | 1383 | 540 | 458 | promotion_blocked_no_repeatable_candidate | False | defensive_rotation |
| 2026-06-22 | 3 | 3 | 3 | 0 | 33.3% | -0.56% | 416 | 267 | 232 | promotion_blocked_no_repeatable_candidate | False | us_tech_risk_on_korea_weak |
| 2026-06-23 | 1 | 1 | 1 | 0 | 0.0% | -3.20% | 528 | 178 | 148 | promotion_blocked_no_repeatable_candidate | False | risk_off_breadth_collapse |
| 2026-06-24 | 3 | 3 | 3 | 0 | 0.0% | -2.88% | 964 | 232 | 215 | promotion_blocked_no_repeatable_candidate | False | macro_pressure_no_trade |
| 2026-06-25 | 1 | 1 | 1 | 0 | 0.0% | -1.72% | 1788 | 621 | 591 | promotion_blocked_no_repeatable_candidate | False | risk_off_breadth_collapse |
| 2026-06-26 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 465 | 140 | 122 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-06-29 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 0 | 0 | 0 | promotion_blocked_sample_or_coverage | False | neutral_observation |
| 2026-06-30 | 2 | 2 | 2 | 0 | 0.0% | -1.35% | 600 | 270 | 242 | promotion_blocked_no_repeatable_candidate | False | liquidity_leader_rotation |
| 2026-07-01 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 3453 | 1237 | 1218 | promotion_blocked_no_repeatable_candidate | False | us_tech_risk_on_korea_weak |
| 2026-07-02 | 9 | 9 | 9 | 0 | 0.0% | -1.09% | 480 | 232 | 217 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-03 | 2 | 0 | 0 | 0 | 0.0% | 0.00% | 666 | 190 | 162 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-06 | 2 | 2 | 2 | 0 | 0.0% | -0.89% | 1219 | 531 | 494 | promotion_blocked_no_repeatable_candidate | False | defensive_rotation |
| 2026-07-07 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 804 | 269 | 238 | promotion_blocked_no_repeatable_candidate | False | us_tech_risk_on_korea_weak |
| 2026-07-08 | 5 | 5 | 5 | 0 | 0.0% | -1.48% | 509 | 201 | 184 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-09 | 2 | 2 | 2 | 0 | 0.0% | -1.57% | 1255 | 435 | 381 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-07-10 | 12 | 12 | 12 | 0 | 25.0% | -0.52% | 2059 | 998 | 933 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-07-13 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 802 | 205 | 172 | promotion_blocked_no_repeatable_candidate | False | us_tech_risk_on_korea_weak |
| 2026-07-14 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 702 | 221 | 175 | promotion_blocked_no_repeatable_candidate | False | risk_off_breadth_collapse |
| 2026-07-15 | 7 | 7 | 7 | 0 | 14.3% | 0.06% | 2336 | 803 | 705 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-07-16 | 4 | 4 | 4 | 0 | 0.0% | -0.88% | 435 | 205 | 184 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-17 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 563 | 14 | 0 | promotion_blocked_sample_or_coverage | False | krx_night_futures_gap_down |
| 2026-07-20 | 1 | 1 | 1 | 0 | 100.0% | 1.41% | 616 | 343 | 321 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-21 | 1 | 1 | 1 | 0 | 0.0% | -0.92% | 1949 | 884 | 816 | promotion_blocked_no_repeatable_candidate | False | neutral_observation |
| 2026-07-22 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 2435 | 661 | 581 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-07-23 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 2271 | 537 | 465 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-07-24 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 781 | 240 | 208 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-27 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1062 | 287 | 260 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-28 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 728 | 266 | 246 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-29 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 886 | 362 | 318 | promotion_blocked_no_repeatable_candidate | False | defensive_rotation |
| 2026-07-30 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1922 | 429 | 393 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-07-31 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1791 | 820 | 762 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-08-03 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1435 | 524 | 496 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-08-04 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1011 | 500 | 451 | promotion_blocked_no_repeatable_candidate | False | liquidity_leader_rotation |
| 2026-08-05 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1697 | 589 | 507 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-08-06 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1169 | 456 | 425 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-08-07 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1674 | 582 | 514 | promotion_blocked_no_repeatable_candidate | False | defensive_rotation |
| 2026-08-10 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1357 | 626 | 549 | promotion_blocked_no_repeatable_candidate | False | liquidity_leader_rotation |
| 2026-08-11 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 2339 | 500 | 453 | promotion_blocked_no_repeatable_candidate | False | macro_pressure_no_trade |
| 2026-08-12 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 537 | 287 | 248 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-08-13 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1275 | 510 | 426 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-08-14 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1654 | 417 | 349 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-08-17 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 598 | 20 | 0 | promotion_blocked_sample_or_coverage | False | neutral_observation |
| 2026-08-18 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 1539 | 293 | 262 | promotion_blocked_no_repeatable_candidate | False | defensive_rotation |
| 2026-08-19 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 518 | 140 | 133 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_down |
| 2026-08-20 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 2135 | 799 | 703 | promotion_blocked_no_repeatable_candidate | False | krx_night_futures_gap_up |
| 2026-08-21 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 940 | 288 | 264 | promotion_blocked_no_repeatable_candidate | False | defensive_rotation |

## Q8 Promotion Eligibility

- status: `promotion_blocked_by_trust_gate_or_legacy_data`
- trusted gate days: **49**
- promotion allowed days: **0**
- rule: Historical conclusions require daily evaluation_trust_gate.promotion_allowed=true. Legacy daily summaries without trust gate are observation-only.

## Trade Pattern Evidence

### By Tactic

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| defensive_observe | 59 | 6.9% | -1.066% |
| opening_range_breakout | 22 | 9.1% | -0.869% |
| vwap_reclaim_pullback | 14 | 14.3% | -0.947% |
| volume_breakout | 10 | 20.0% | -0.313% |

### By Entry Reason

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| 진입 사유는 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파입니다 | 6 | 0.0% | -1.083% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 005360이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 2 | 100.0% | 4.922% |
| 진입 사유는 Entry evidence was 기록되지 않음 for this day. Position context was inferred from downstream monitor/exit artifacts.입니다 | 2 | 0.0% | -1.670% |
| 진입 사유는 hold입니다 | 2 | 0.0% | -1.395% |
| 진입 사유는 VWAP 위 눌림목 구조와 거래량 확인입니다 | 2 | 0.0% | -1.122% |
| 진입 사유는 human chart entry setup confirmed입니다 | 2 | 0.0% | -1.067% |
| 진입은 VWAP 위 눌림목 구조와 거래량 확인 조건에서 실행됐습니다. 052420이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 2 | 0.0% | -0.835% |
| 진입 사유는 직전 고점 돌파와 VWAP 구조 확인이었습니다 | 2 | 50.0% | 0.662% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 스캐너 상위 후보 089030은 breakout not ready 이유로 보류됐고 122630 차순위 재평가 6위 진입으로 전환됐습니다. 실제 트리거는 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파였습니다 | 1 | 100.0% | 6.480% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 스캐너 상위 후보 035420은 below vwap reclaim not ready 이유로 보류됐고 034220 차순위 재평가 4위 진입으로 전환됐습니다. 실제 트리거는 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파였습니다 | 1 | 0.0% | -4.630% |

### By Exit Reason

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| 추세 훼손 | 33 | 3.0% | -0.834% |
| 고정 손절 기준 | 30 | 0.0% | -2.066% |
| VWAP 이탈 | 7 | 14.3% | -0.959% |
| 거래량 둔화 익절 | 5 | 100.0% | 3.668% |
| SELL reconciled from Kiwoom day trade diary. | 5 | 0.0% | -1.606% |
| 장마감 정리 기준 | 3 | 0.0% | -0.752% |
| 목표 수익 실현 기준 | 2 | 50.0% | 0.705% |
| 추적 손절 기준 | 1 | 0.0% | -1.410% |
| 고점 대비 하락폭 기준 | 1 | 0.0% | -0.087% |
| Executor recorded SELL, but the monitor had not confirmed the exit yet (hold). This is a monitor/executor mismatch, n | 1 | 0.0% | 0.000% |

## Q8 Shadow Summary

- Q8 shadow summary days: **60**
- Q8 blocker forward-review days: **58**

### Top Shadow Reasons

| Reason | Count |
| --- | --- |
| below_vwap_reclaim_not_ready | 14934 |
| rank_above_cascade_limit | 14485 |
| pullback_not_mature | 6355 |
| breakout_not_ready | 5705 |
| volume_confirmation_missing | 4413 |
| q15_runner_up_expected_blocker | 4251 |
| pullback_below_vwap_reclaim_not_ready | 3763 |
| volume_insufficient | 2902 |
| too_extended_from_vwap | 1794 |
| breakout_above_recent_high_with_vwap_hold_and_volume_confirmation | 1736 |
| quant_entry_block:cost_edge_fail | 1331 |
| human_chart_sanity_guard_blocked | 1217 |
| q15_score_gap_above_runner_up_limit | 791 |
| minute_candle_missing | 565 |
| breakout_above_recent_high_with_vwap_structure_confirmation | 402 |

### Forward Blocker Review

| Reason | n | obs | Latest | MFE | MAE | Missed | Adverse | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| below_vwap_reclaim_not_ready | 6765 | 6260 | -0.0109% | 1.2787% | -1.2368% | 40.1% | 63.1% | retain_under_observation |
| breakout_not_ready | 2929 | 2772 | 0.0065% | 1.0944% | -1.0773% | 35.9% | 59.8% | retain_under_observation |
| pullback_not_mature | 2582 | 2374 | -0.0939% | 0.8881% | -0.9999% | 30.6% | 59.8% | retain_under_observation |
| volume_confirmation_missing | 1884 | 1732 | -0.0633% | 1.7213% | -1.6906% | 46.9% | 71.5% | retain_under_observation |
| human_chart_sanity_guard_blocked | 748 | 689 | 0.0869% | 1.6437% | -1.6562% | 44.1% | 70.7% | retain_under_observation |

## Below-VWAP Reclaim Subtype Review

- Subtype count days: **60**
- Subtype forward days: **51**
- Note: subtype forward evidence is available only after the entry-lane observation fields were added.

### Subtype Counts

| Subtype | Count |
| --- | --- |
| true_below_vwap_failure | 15674 |
| near_vwap_reclaim_setup | 1256 |
| reclaim_in_progress_with_improving_volume | 466 |
| post_reclaim_pullback_candidate | 92 |

### Subtype V2 Counts

| Subtype V2 | Count |
| --- | --- |
| deep_below_vwap_failure | 9070 |
| ordinary_below_vwap_failure | 4811 |
| shallow_below_vwap_rebound | 2285 |
| near_vwap_reclaim_setup | 523 |
| confirmed_post_reclaim_pullback | 91 |

### Subtype Forward Outcomes

| Subtype | n | obs | 3m | 5m | 15m | 30m | 60m | MFE5 | MAE5 | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vwap_reclaim:true_below_vwap_failure | 6638 | 6192 | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | retain_under_observation |
| vwap_reclaim:near_vwap_reclaim_setup | 637 | 607 | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | retain_under_observation |
| vwap_reclaim:reclaim_in_progress_with_improving_volume | 225 | 200 | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | retain_under_observation |
| vwap_reclaim:post_reclaim_pullback_candidate | 32 | 31 | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% | retain_under_observation |

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
