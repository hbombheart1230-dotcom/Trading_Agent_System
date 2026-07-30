# Q8-Q17 Canonical Final Review - 2026-07-30

## 결론

Q8부터 평가를 다시 시작하지 않는다.

테스트 오염을 제거한 canonical artifact로 2026-06-01부터
2026-07-30까지 다시 집계했으며, Q8-Q17의 평가 개발은 종료한다.
이후에는 이미 적용된 정책의 자연 발생 이벤트를 확인하고, 유일한
양수 연구 후보 하나만 제한적으로 검토한다.

현재 결론은 다음과 같다.

1. 기존 실현 매매는 수익성이 없었다.
2. Scanner Rank 1은 하위 순위보다 상대적으로 낫지만 비용 차감 후
   절대 기대값은 음수다.
3. Strategist의 순위 개입은 Scanner 원본 대비 알파를 입증하지 못했다.
4. Commander가 임의로 종목을 바꿨다는 증거는 없다.
5. Q10-Q12 단순 통제 전략도 수익성이 없어, 무거래가 곧 명백한
   기회손실이라는 근거는 없다.
6. Q15, Q16 및 당일 동일 종목 손실 재진입 차단은 손실 억제 정책으로
   유지한다.
7. `confirmed_post_reclaim_pullback`만 실계좌 비용 기준 양수인
   shadow 연구 후보로 남긴다.
8. Q17 directional-edge 계약과 horizon 계약은 코드·artifact·테스트
   기준으로 복구됐지만, 실제 체결 후 수익성은 아직 입증되지 않았다.
9. Q18과 같은 새 평가 프로그램을 만들지 않는다.

## 권위 데이터

이번 문서의 수치는 다음 순서로 해석한다.

1. Kiwoom broker truth
2. clean daily ledger와 daily scorecard
3. Q9 정규장 P/A/B/C 및 forward artifact
4. Q13/Q14 frozen read model
5. Q8 shadow 및 Q10-Q12 통제군

서로 다른 read model의 표본 수는 합치지 않는다.

| 모집단 | 표본 | 용도 |
| --- | ---: | --- |
| Daily scorecard finite return | 97 | 실현 성과 |
| Q13 scored trades | 107 | attribution 점수 |
| Q14 root-cause trades | 105 | scanner alignment 원인 분류 |
| Same-symbol trusted entries | 99 | 재진입 분석 |
| Scanner independent episodes | 14,067 | 후보 순위 forward 성과 |

테스트 오염 제거 결과:

| 항목 | 제거 |
| --- | ---: |
| 합성 Q9 decision windows | 311 |
| 합성 quant-shadow JSON | 542 |
| 테스트 event rows | 12,493 |
| 폐기된 pytest event log | 2,455,323,300 bytes |

정리 후 dry-run 재검사는 Q9, shadow, event 모두 0건이었다.

## 실현 성과

| 기간 | 거래 | 승 | 패 | 보합 | 승률 | 평균 수익률 | Profit Factor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6월 | 56 | 5 | 50 | 1 | 8.93% | -1.1293% | 0.1822 |
| 7월 | 41 | 5 | 36 | 0 | 12.20% | -0.7277% | 0.3047 |
| 합계 | 97 | 10 | 86 | 1 | 10.31% | -0.9595% | 0.2259 |

누적 단순 합산 수익률은 -93.0743%다. 이는 동일 자본 복리 수익률이
아니라 거래별 수익률 합계이며, 시스템의 과거 기대값이 크게
음수였다는 진단 용도로만 사용한다.

7월은 6월보다 개선됐지만 profitable regime으로 전환되지는 않았다.
거래 수를 다시 늘리는 근거는 없다.

## Scanner

30초 단위 반복 후보를 독립 표본으로 취급하지 않고 15분 episode로
압축했다.

- raw candidate rows: 64,253
- independent episodes: 14,067
- score-component forward observations: 544
- component-covered episodes: 164
- component coverage: 30.15%, 3일

실계좌 비용 0.28% 차감 후:

| Rank | +5m | +15m | +30m | EOD |
| --- | ---: | ---: | ---: | ---: |
| Rank 1 | -0.2531% | -0.1905% | -0.3466% | -1.8092% |
| Rank 2-3 | -0.4248% | -0.5009% | -0.5156% | -6.0876% |
| Rank 4+ | -0.3725% | -0.4195% | -0.3239% | -3.3999% |

해석:

- Rank 1은 +5m/+15m에서 상대적으로 가장 낫다.
- Rank 1 자체도 비용 차감 후 음수다.
- 하위 순위로 교체하는 것은 해결책이 아니다.
- 현재 문제는 단순 rank ordering뿐 아니라 후보의 절대 edge 부족이다.
- score component coverage가 3일뿐이므로 Scanner 가중치 변경은
  아직 허용하지 않는다.

## Strategist와 Commander

동일 Scanner universe에서 Strategist B와 Scanner A를 비교한 결과:

| Horizon | 관측일 | B 우세일 | B 열세일 | B-A 평균 |
| --- | ---: | ---: | ---: | ---: |
| +5m | 26 | 12 | 13 | -0.0026% |
| +15m | 26 | 12 | 13 | -0.0588% |
| +30m | 26 | 13 | 12 | -0.0285% |
| EOD | 22 | 9 | 13 | -0.2602% |

Strategist는 순위 알파를 입증하지 못했다. 그렇다고 Strategist를
제거하지는 않는다. Strategist의 scenario, horizon, risk, 설명 역할은
후보 sourcing과 별개다. 다만 순위 개입이 유리하다고 가정해서는 안 된다.

Q13 selection integrity 평균은 95.15점이다. Commander가 Scanner 후보를
자의적으로 다른 종목으로 교체했다는 증거는 없다. Commander reject가
상대적으로 좋아 보이는 경우에는 현금 수익률 0% 효과가 포함되므로,
이를 양의 selection alpha로 해석하지 않는다.

## Q13-Q14 진단

Q13 최신 frozen 집계:

| Axis | 평균 | Scored Days | 결론 |
| --- | ---: | ---: | --- |
| selection_integrity_score | 95.15 | 27 | 안정적 |
| scanner_alignment_score | 72.07 | 27 | 가장 반복적인 약점 |
| entry_timing_score | 83.00 | 9 | 표본 부족, 1순위 원인 아님 |
| exit_horizon_score | 78.44 | 27 | 반복 약점 |
| evidence_quality_score | 93.29 | 28 | 정제 후 안정적 |

Q14 최신 집계:

| Root Cause | 성격 | 거래 | 평균 수익률 | 해석 |
| --- | --- | ---: | ---: | --- |
| Scanner Ranking Failure | outcome-conditioned | 22 | -1.5531% | 결과 라벨, 단독 행동 근거 아님 |
| Candidate Filtering | structural | 17 | -0.9645% | Q15 대상 |
| Strategist Override | structural | 9 | -0.9208% | 진단 후보 |
| Missing Evidence | evidence gap | 54 | -0.9587% | 과거 artifact 시대 한계 |
| Aligned / No Alignment Issue | outcome-conditioned | 3 | +3.3110% | 양의 상대군 |

`scanner_alignment_score`가 낮다는 말은 "Scanner 1위가 항상 나쁘다"와
"다른 후보가 선택됐다"를 섞는 뜻이 아니다. Q14가 이를 ranking outcome,
candidate filtering, strategist override, evidence gap으로 분리한다.

## Q8-Q17 타임라인

| Phase | 확인한 것 | 최종 상태 | 다시 평가할 필요 |
| --- | --- | --- | --- |
| Q8 | tactic lane, VWAP, pullback, volume, opening, runner-up shadow | CLOSED | 없음 |
| Q9 | P/A/B/C와 Scanner 후보 절대 edge | DIAGNOSIS COMPLETE | 누적만 계속 |
| Q10 | 삼성전자/하이닉스 단순 baseline | CONTROL RETAINED | 행동 승격 없음 |
| Q11 | 장초반 surge/probe baseline | CONTROL RETAINED | 행동 승격 없음 |
| Q12 | BTC/우리기술투자 baseline | CONTROL RETAINED | 행동 승격 없음 |
| Q13 | selection/scanner/entry/exit/evidence attribution | FROZEN | 산식 변경 없음 |
| Q14 | scanner alignment root cause | FROZEN | 산식 변경 없음 |
| Q15 | 약한 runner-up cascade 제한 | RETAIN | 처음부터 재검증 없음 |
| Q16 | ATR/변동성 proxy를 directional edge로 인정하지 않음 | RETAIN | 처음부터 재검증 없음 |
| Q17 | horizon-matched directional evidence 계약 | CONTRACT REPAIRED | 자연 발생 smoke만 |

## Q10-Q12 통제군

2026-07-30 EOD까지 일별 artifact를 직접 재합산했다. 아래 값은
mock-observed 비용 1.086849%가 적용된 shadow entry 결과다.

| Control | Entries | Days | +5m | +15m | +30m | EOD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q10 Samsung/Hynix | 456 | 16 | -1.1519% | -1.1463% | -1.0426% | -1.0638% |
| Q11 Opening Probe v0 | 71 | 20 | - | - | -1.3720% policy result | - |
| Q12 BTC/Woori | 185 | 23 | -1.2313% | -1.2697% | -1.3523% | -1.6463% |

단순 대형주 momentum, 장초반 probe, BTC 선행 신호 어느 것도 주 시스템을
대체할 수익성을 보이지 않았다.

## 확정 유지 정책

### Q15 Runner-Up Control

- 실제 fallback은 기본 rank 3 이내
- Top1 대비 score gap 0.20 이내
- 명백한 blocker가 있는 runner-up은 cascade 금지
- 예상 `volume_insufficient`만 pre-veto에서 제거
- Monitor의 현재 거래량 hard gate는 유지

Q15는 Rank 1을 수익 전략으로 선언한 것이 아니다. Rank 1이 준비되지
않았을 때 더 약한 후보로 새는 손실을 막는 정책이다.

### Q16 Directional Evidence

ATR과 변동성은 움직임 크기이지 방향 기대값이 아니다. 따라서
`allow_triggered_signal_proxy_edge=false`를 유지한다.

정제 후 Q16 exact proxy-only 결과:

- exact rejections: 156
- +30m observations: 83
- observed days: 5
- positive days: 1
- +30m live-net average: +0.0720%
- +30m live-net profit factor: 1.1403

누적 평균이 소폭 양수인 이유는 2026-07-23의 +0.6919%가 크기 때문이다.
나머지 관측일은 음수였고 2026-07-30도 -0.4019%였다. 사전 rollback
조건인 반복적인 일별 양수 결과를 충족하지 못하므로 Q16은 `RETAIN`이다.

과거 Q16 close 문서의 2026-07-24 forward 45건은 테스트 오염 제거 후
canonical 관측 0건으로 정정됐다. 정책 결정은 이후 clean 관측일까지
포함해도 유지되지만, 이전의 -0.0401% 누적값은 더 이상 권위값이 아니다.

### Same-Symbol Loss Reentry

| Cohort | Count | 승률 | 평균 | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| First entry | 72 | 13.89% | -0.8506% | 0.3072 |
| Repeat entry | 27 | 3.70% | -1.2478% | 0.0026 |
| Repeat after loss | 24 | 4.17% | -1.2756% | 0.0029 |

전량 손실 청산 후 같은 날 같은 종목의 재진입만 차단한다. 수익·보합,
부분 청산, 손익 미확정, 다른 종목, 다음 거래일에는 적용하지 않는다.

## 유일한 Alpha 연구 후보

`confirmed_post_reclaim_pullback`:

- candidates: 27
- observed: 26
- observed days: 14
- coverage: 96.3%

| Horizon | Gross | Live Net 0.28% | Mock Net 1.086849% |
| --- | ---: | ---: | ---: |
| +5m | +0.3127% | +0.0327% | -0.7741% |
| +15m | +0.4355% | +0.1555% | -0.6513% |
| +30m | +0.5247% | +0.2447% | -0.5621% |
| +60m | +0.4935% | +0.2135% | -0.5933% |

현재 상태는 `LIVE_COST_SHADOW_CANDIDATE`다. 아직 공식 정책은 아니다.

미승격 사유:

- 26건은 작다.
- 같은 종목·인접 시점의 serial correlation 가능성이 남는다.
- episode-level profit factor와 drawdown이 아직 promotion artifact에 없다.
- mock 비용에서는 전 구간 음수다.
- Q17 runtime directional evidence와 연결되지 않았다.

다음 행동 후보는 이것 하나뿐이다. broad VWAP 완화나 pullback 전체
완화는 하지 않는다.

## Q17과 Horizon의 남은 검증

Q17 계약은 복구됐다.

- runtime memory path가 실제 state 구조와 일치한다.
- scalp는 +5m, intraday는 +30m를 사용한다.
- overnight는 next-open, 1-2 day swing은 +1 trading day evidence 없이는
  fail closed한다.
- short checkpoint를 장기 horizon 증거로 오인하지 않는다.

2026-07-27 이후 관측:

| Q17 Class | Count |
| --- | ---: |
| Directional estimate artifact missing | 81 |
| Directional evidence unavailable | 40 |
| Directional below-cost rejection | 11 |
| Directional admitted | 0 |

below-cost class 중 forward가 있는 10건은 +30m live-net 평균 +0.4634%,
profit factor 3.4571이었다. 이는 Q17 threshold calibration을 다시 볼
수 있는 경고지만, 10건의 연속 관측과 admitted 비교군 0건으로 정책을
바꿀 근거는 아니다.

남은 확인은 새 평가 프로그램이 아니다.

1. 다음 자연 발생 진입에서 BUY 시점 horizon이 position context에
   고정되는지 확인한다.
2. 청산까지 같은 horizon이 유지되는지 확인한다.
3. soft exit가 min hold를 위반하지 않는지 확인한다.
4. hard stop과 emergency exit는 min hold와 독립인지 확인한다.
5. Q17 evidence source, horizon, expected move가 cost filter까지 이어지는지
   확인한다.

거래를 만들기 위해 조건을 완화하지 않는다.

## 2026-07-30 무거래 판단

Q9 정규장 상태:

- validity: `VALID`
- formal windows: 596
- linked P/A/B/C: 596
- linkage: 100%
- synthetic windows: 0
- post-session windows: 74, formal denominator에서 제외
- forward usable coverage: 99.35%

무거래 원인:

- Commander approve 후 Monitor NOOP: 373
- Commander reject: 222
- 주요 Monitor NOOP:
  - below-VWAP reclaim not ready: 337
  - volume confirmation missing: 72
  - pullback not mature: 62
  - breakout not ready: 55
  - cost-adjusted edge not ready: 33

당일 통제군:

- Q10 +30m: -1.0336%
- Q11 policy result: -1.5073%
- Q12 +30m: -1.0081%
- Q16 exact rejected +30m: -0.4019%

따라서 2026-07-30 무거래는 오류나 명백한 기회손실로 판정하지 않는다.
다만 모든 approve+NOOP를 성공적인 over-filtering으로 간주하지도 않는다.
공식 판정은 `FILTERING_REVIEW_REQUIRED`다.

## 무엇이 끝났고 무엇이 남았는가

### 종료

- Q8 broad tactic promotion
- Q9 원인 분해
- Q10-Q12 대체 baseline 비교
- Q13/Q14 평가 축 개발
- Q15 runner-up 누수 수정
- Q16 volatility proxy 수정
- 테스트/운영 artifact 오염 정리

### 유지

- 낮은 거래 빈도
- cost/volume/VWAP/pullback hard evidence
- Q15 runner-up 제한
- Q16 directional evidence 요구
- 당일 동일 종목 손실 재진입 차단

### 자연 발생 이벤트에서만 확인

- Q17 directional evidence end-to-end
- 실제 position horizon 고정과 청산 준수
- same-symbol loss reentry block runtime smoke

### 다음 단일 연구

- `confirmed_post_reclaim_pullback` episode-level promotion review

## 최종 실행 순서

1. 현 행동 정책을 유지한 채 정상 런을 수행한다.
2. 매일 기존 Q8-Q17 및 Q9 누적 산출물만 자동 갱신한다.
3. 자연 거래가 발생하면 Q17/horizon/reentry smoke를 확인한다.
4. 별도로 post-reclaim 후보를 15분 독립 episode로 재집계한다.
5. episode profit factor, drawdown, 일별 편중, 종목 편중을 확인한다.
6. 통과하면 해당 subtype 하나만 제한적으로 승격 검토한다.
7. 실패하면 후보를 기각하고 broad relaxation 없이 현재 방어 정책을
   유지한다.

평가 체계를 다시 만들거나 기간을 처음부터 세지 않는다. 앞으로 필요한
것은 기존 clean evaluator를 이용한 전후 비교와 단일 후보 결정이다.
