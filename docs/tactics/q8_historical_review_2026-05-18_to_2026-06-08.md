# Q8 Historical Review: 2026-05-18 to 2026-06-08

> Legacy evidence warning: this report was generated before the 2026-06-16 Q8
> Evaluation Contract. Use it as observation history only unless regenerated
> with canonical dedupe, trusted same-day forward outcomes, and
> `evaluation_trust_gate.promotion_allowed=true`.

Purpose: reuse prior live and shadow evidence without mixing incompatible artifact eras.

This review is evaluation-only. It does not change entry, exit, scanner, Strategist, or execution behavior.

## Data Windows

- Live trade performance: usable from 2026-05-18 onward when truth-surface PnL exists.
- Q8 shadow evaluation: most useful from 2026-05-26 onward when candidate shadow summaries are populated.
- Market regime rail: most useful from 2026-06-02 onward when rail IDs are attached to daily summaries.
- Broker truth reconciliation: strongest from 2026-06-08 onward after post-close order-pair repair.

## Live Trade Summary

- Trade report files: **97**
- Return samples: **97**
- Win rate: **11.34%**
- Average return: **-1.0457%**

| Day | Trades | Closed | Returns | Missing | Win | Avg | Shadow | Rail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-18 | 20 | 20 | 17 | 3 | 11.8% | -1.06% | 0 | - |
| 2026-05-19 | 9 | 9 | 6 | 3 | 0.0% | -1.62% | 0 | - |
| 2026-05-20 | 4 | 3 | 3 | 0 | 0.0% | -1.76% | 0 | - |
| 2026-05-21 | 8 | 6 | 6 | 0 | 50.0% | -0.41% | 0 | - |
| 2026-05-22 | 8 | 8 | 7 | 1 | 28.6% | -0.97% | 0 | - |
| 2026-05-25 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 0 | - |
| 2026-05-26 | 6 | 4 | 4 | 0 | 0.0% | -1.11% | 935 | - |
| 2026-05-27 | 9 | 9 | 9 | 0 | 0.0% | -1.56% | 1594 | - |
| 2026-05-28 | 5 | 5 | 5 | 0 | 0.0% | -2.05% | 1199 | - |
| 2026-05-29 | 7 | 6 | 6 | 0 | 16.7% | -0.39% | 908 | - |
| 2026-06-01 | 7 | 7 | 7 | 0 | 0.0% | -1.52% | 1157 | - |
| 2026-06-02 | 1 | 1 | 1 | 0 | 0.0% | -1.20% | 1474 | us_tech_risk_on_korea_weak |
| 2026-06-03 | 0 | 0 | 0 | 0 | 0.0% | 0.00% | 0 | - |
| 2026-06-04 | 1 | 1 | 1 | 0 | 0.0% | -1.79% | 1144 | risk_off_breadth_collapse |
| 2026-06-05 | 2 | 2 | 2 | 0 | 0.0% | -1.14% | 872 | risk_off_breadth_collapse |
| 2026-06-08 | 12 | 12 | 12 | 0 | 8.3% | -0.88% | 777 | krx_night_futures_gap_down |

## Trade Pattern Evidence

### By Tactic

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| vwap_reclaim_pullback | 53 | 3.8% | -1.290% |
| defensive_observe | 32 | 6.2% | -1.110% |
| opening_range_breakout | 12 | 45.5% | -0.474% |
| opening_gap_momentum | 2 | 0.0% | -0.716% |

### By Entry Reason

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| 진입 사유는 hold입니다 | 8 | 12.5% | -1.284% |
| 진입 사유는 VWAP 위 눌림목 구조와 거래량 확인입니다 | 4 | 0.0% | -1.225% |
| 오늘 신규 진입 판단이 아니라 전일/주말 이월 포지션입니다. | 4 | 0.0% | -0.367% |
| 진입 사유는 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파입니다 | 3 | 66.7% | 0.408% |
| 진입은 직전 고점 돌파와 VWAP 구조 확인 조건에서 실행됐습니다. 000660이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 2 | 0.0% | -1.790% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 000660이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 2 | 0.0% | -1.480% |
| 진입은 VWAP 유지와 거래량 확인이 있는 최근 고점 돌파 조건에서 실행됐습니다. 005930이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 2 | 0.0% | -1.090% |
| 진입은 VWAP 위 눌림목 구조와 거래량 확인 조건에서 실행됐습니다. 스캐너 상위 후보 396500은 눌림목 not mature 이유로 보류됐고 000660 차순위 재평가 3위 진입으로 전환됐습니다. 실제 트리거는 VWAP 위 눌림목 구조와 거래량 확인이었습니다 | 2 | 0.0% | -1.085% |
| 진입은 VWAP 위 눌림목 구조와 거래량 확인 조건에서 실행됐습니다. 005930이 스캐너 1위 후보로 올라온 뒤 매수로 이어졌습니다 | 2 | 0.0% | -0.861% |
| 진입은 VWAP 위 눌림목 구조와 거래량 확인 조건에서 실행됐습니다. 스캐너 상위 후보 396500은 눌림목 not mature 이유로 보류됐고 005930 차순위 재평가 5위 진입으로 전환됐습니다. 실제 트리거는 VWAP 위 눌림목 구조와 거래량 확인이었습니다 | 2 | 0.0% | -0.628% |

### By Exit Reason

| Name | Count | Win | Avg |
| --- | --- | --- | --- |
| 고정 손절 기준 | 27 | 0.0% | -2.234% |
| 추세 훼손 | 23 | 4.3% | -0.915% |
| 장중 저점 이탈 기준 | 20 | 0.0% | -1.125% |
| 거래량 둔화 익절 | 9 | 66.7% | 0.753% |
| VWAP 이탈 | 8 | 12.5% | -1.123% |
| 목표 수익 실현 기준 | 3 | 33.3% | 1.187% |
| 장마감 정리 기준 | 3 | 0.0% | -0.200% |
| 고점 대비 하락폭 기준 | 1 | 0.0% | -0.350% |

## Q8 Shadow Summary

- Q8 shadow summary days: **11**
- Q8 blocker forward-review days: **4**

### Top Shadow Reasons

| Reason | Count |
| --- | --- |
| below_vwap_reclaim_not_ready | 3940 |
| pullback_not_mature | 1942 |
| volume_confirmation_missing | 1098 |
| breakout_not_ready | 662 |
| minute_candle_missing | 429 |
| pullback_below_vwap_reclaim_not_ready | 411 |
| volume_insufficient | 255 |
| human_chart_sanity_guard_blocked | 230 |
| breakout_above_recent_high_with_vwap_hold_and_volume_confirmation | 225 |
| breakout_above_recent_high_with_vwap_structure_confirmation | 141 |
| human_chart_entry_setup_confirmed | 50 |
| too_extended_from_vwap | 45 |
| excluded_same_symbol_or_pending_buy | 43 |
| pullback_structure_above_vwap_with_volume_confirmation | 38 |
| quant_entry_block:vwap_pullback_promoted_quality_gate | 29 |

### Forward Blocker Review

| Reason | n | obs | Latest | MFE | MAE | Missed | Adverse | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| below_vwap_reclaim_not_ready | 991 | 919 | 0.2906% | 1.3626% | -1.0407% | 44.9% | 59.1% | retain_under_observation |
| breakout_not_ready | 334 | 315 | -0.2367% | 0.9855% | -1.1764% | 31.1% | 69.2% | adjust_and_retest |
| pullback_not_mature | 244 | 231 | -0.0702% | 0.8127% | -0.7646% | 30.3% | 52.8% | adjust_and_retest |
| volume_confirmation_missing | 179 | 168 | -0.4923% | 1.1853% | -1.8430% | 43.5% | 76.8% | retain_under_observation |
| human_chart_sanity_guard_blocked | 92 | 90 | -0.4767% | 0.6957% | -2.1166% | 26.7% | 76.7% | promotion_review_target |

## Below-VWAP Reclaim Subtype Review

- Subtype count days: **11**
- Subtype forward days: **2**
- Note: subtype forward evidence is available only after the entry-lane observation fields were added.

### Subtype Counts

| Subtype | Count |
| --- | --- |
| true_below_vwap_failure | 595 |
| near_vwap_reclaim_setup | 70 |
| reclaim_in_progress_with_improving_volume | 42 |
| post_reclaim_pullback_candidate | 1 |

### Subtype V2 Counts

| Subtype V2 | Count |
| --- | --- |
| deep_below_vwap_failure | 2004 |
| ordinary_below_vwap_failure | 1339 |
| shallow_below_vwap_rebound | 741 |
| near_vwap_reclaim_setup | 211 |
| index_or_largecap_rebound_below_vwap | 95 |
| confirmed_post_reclaim_pullback | 12 |

### Subtype Forward Outcomes

| Subtype | n | obs | 3m | 5m | 15m | 30m | 60m | MFE5 | MAE5 | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vwap_reclaim:true_below_vwap_failure | 590 | 535 | 0.0444% | 0.1031% | 0.3762% | 0.7208% | 1.4628% | 0.5336% | -0.3782% | review_classifier_or_label |
| vwap_reclaim:near_vwap_reclaim_setup | 70 | 67 | -0.0167% | 0.0218% | -0.2083% | -0.4298% | -0.0821% | 0.3981% | -0.3962% | retain_under_observation |
| vwap_reclaim:reclaim_in_progress_with_improving_volume | 42 | 37 | 0.0254% | -0.0704% | -0.1925% | -0.2157% | 0.1667% | 0.3438% | -0.3275% | keep_blocked |

## Recommendations

| Candidate | Decision | Evidence |
| --- | --- | --- |
| risk_off_defensive_observe_no_entry_policy | promoted_keep | defensive_observe live trades are negative and 2026-06-08 showed severe risk-off misuse. |
| below_vwap_reclaim_not_ready | subtype_adjust_review | n=991, obs=919, latest=0.2906%, missed=44.9%, adverse=59.1% |
| breakout_not_ready | adjust_and_retest | n=334, obs=315, latest=-0.2367%, missed=31.1%, adverse=69.2% |
| pullback_not_mature | adjust_and_retest | n=244, obs=231, latest=-0.0702%, missed=30.3%, adverse=52.8% |
| volume_confirmation_missing | retain_strict_or_observe | n=179, obs=168, latest=-0.4923%, missed=43.5%, adverse=76.8% |
| human_chart_sanity_guard_blocked | retain_veto_review_missed | n=92, obs=90, latest=-0.4767%, missed=26.7%, adverse=76.7% |
| below_vwap_reclaim_subtype_policy | do_not_relax_globally | Subtype forward evidence is mixed; strongest=vwap_reclaim:true_below_vwap_failure 5m=0.1031%, 15m=0.3762%. Review classifier labels before behavior promotion. |

## Operator Conclusion

- Prior data is useful, but it must be sliced by artifact era.
- Live trade PnL already shows persistent negative expectancy in stop/trend-break/low-break exits.
- Q8 raw shadow sample size alone is not promotion evidence under the 2026-06-16 Q8 Evaluation Contract.
- Continue using 2026-05-26 onward for shadow blocker evidence, and 2026-06-02 onward for rail-aware evaluation.
