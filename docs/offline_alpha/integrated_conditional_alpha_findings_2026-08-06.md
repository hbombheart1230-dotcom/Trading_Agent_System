# 통합 조건부 알파 오프라인 분석

## 목적과 범위

이 문서는 장초반 슈팅, Scanner Rank-1의 조건부 보유시간, 후일 재점화를 하나의 진단 체계로 연결한다.

- 분석 범위: 2026년 6~7월 자료
- 장초반 Rank-1 사례: 65건
- 실제 거래 horizon 비교: 100건
- Quant Trade Diagnosis 재생성: 107개 거래 bundle
- 행동 변경: 없음
- 미래 수익률은 평가 label로만 사용하며 입력 feature로 사용하지 않음

## 가장 중요한 결론

1. Scanner Rank-1 전체를 매수하는 엣지는 확인되지 않았다.
2. 장초반 0~5분 전체는 15분과 30분에서 양수였지만 상위 사례 의존성이 크다.
3. 5~20분 구간 전체는 오히려 손실이었다. 다만 `이전 Rank-1 관측 + 완료된 1분봉 양수` 조건은 별도 가능성이 있다.
4. 극단적 거래량은 성공 조건이 아니었다. 성공군의 상대 거래량은 실패군보다 낮았다.
5. Scanner 점수와 confidence만으로는 성공·실패가 거의 구분되지 않았다.
6. 동일 종목의 후일 급등은 원래 포지션을 계속 보유할 근거가 아니라 새 신호로 재평가할 대상이다.
7. 현재 가장 큰 계측 공백은 Commander 승인 후 Monitor NOOP의 구체 사유다.

## 단계별 30분 성과

| 단계 | N | 승률 | 평균 | PF | 해석 |
|---|---:|---:|---:|---:|---|
| Scanner intrinsic Rank-1 | 65 | 61.54% | +0.7502% | 1.7727 | 조건부 기회는 존재 |
| Strategist 이후 선택 | 65 | 56.92% | +0.4518% | 1.3925 | Scanner 대비 평균 -0.2984%p |
| Monitor 후보 | 64 | 57.81% | +0.5075% | 1.4364 | 후보 교체 단계의 추가 훼손은 작음 |
| 실제 실행 shadow 30m | 2 | 100% | +14.5114% | 999 | 표본 2건, 일반화 금지 |
| 실제 실현 | 2 | 100% | +4.2695% | 999 | 독립 decision 기준 2건 |

실제 거래와 장초반 episode의 정확 decision-ID 연결은 독립 진입 2개뿐이다. 분할매도 child 1개는 동일 진입의 중복이므로 독립 표본에서 제외한다. 날짜·종목만 같은 20개 거래는 맥락 참고용이며 인과 연결로 사용하지 않는다.

## 단계 귀속 결과

아래 label은 사후 30분 결과를 이용한 진단 분류이며 행동 정책이 아니다.

| 진단 label | N | Scanner 30m 평균 | 의미 |
|---|---:|---:|---|
| NO_INTRINSIC_30M_EDGE | 25 | -2.5243% | Scanner Rank-1 자체가 30분 기준 음수 |
| ENTRY_NOT_EXECUTED_POSITIVE | 17 | +2.6474% | 앞 단계는 양수였으나 승인 후 실행 없음 |
| COMMANDER_FILTERED_POSITIVE | 12 | +0.9297% | 앞 단계 양수, Commander reject/retry |
| STRATEGIST_DEGRADATION | 9 | +3.2678% | Strategist 선택이 Scanner보다 0.28%p 이상 악화 |
| PIPELINE_PRESERVED_OR_EXECUTED | 2 | +13.1499% | Scanner 후보가 실행까지 보존됨 |

이 표를 단순히 합쳐 “차단을 모두 풀자”고 해석하면 안 된다. Commander가 거절한 사례는 사후 양수 17건과 음수 10건이 함께 있었고, 승인 후 미실행 사례도 양수 21건과 음수 14건이 함께 있었다.

## 성공군과 실패군 차이

| Point-in-time 항목 | 30m 양수 40건 | 30m 비양수 25건 | 차이 |
|---|---:|---:|---:|
| Scanner score | 0.9286 | 0.9056 | +0.0230 |
| Confidence | 0.8190 | 0.8030 | +0.0160 |
| Risk score | 0.6487 | 0.6348 | +0.0139 |
| 이전 5분 Rank-1 관측 횟수 | 0.7250 | 0.2800 | +0.4450 |
| 완료된 1분봉 수익률 | +0.3172% | -0.1975% | +0.5147%p |
| 장초반 상대 거래량 | 2.3536x | 5.3240x | -2.9704x |
| 전일 종가 대비 진입 확장 | +1.8766% | +2.9512% | -1.0746%p |

해석:

- 절대 Scanner 점수, confidence, risk 차이는 작다.
- 반복 Rank-1 관측과 완료된 1분봉 방향은 더 큰 차이를 보였다.
- 거래량은 많을수록 좋은 것이 아니었다. 실패군이 평균적으로 과열되어 있었다.
- 이미 많이 확장된 가격을 추격한 경우가 더 나빴다.

## 장초반 시간과 조건부 Horizon

| 조건 | N | 강한 관측 horizon | 평균 | 상위 3건 제외 평균 | 상태 |
|---|---:|---:|---:|---:|---|
| 09:00~09:04 전체 | 26 | 15분 | +2.1489% | +0.2409% | SCREENABLE |
| 0~1분 즉시 포착 | 19 | 15분 | +3.2427% | +0.6630% | SCREENABLE |
| 5~20분 전체 | 32 | 15분 | -0.7052% | -1.0323% | 부정적 |
| 반복 Rank-1 + 완료 1분봉 양수 | 9 | 30분 | +1.4270% | +0.4935% | DESCRIPTIVE_ONLY |
| 위 조건 + 상대 거래량 0.5~4x | 7 | 30분 | +1.6032% | +0.3352% | DESCRIPTIVE_ONLY |
| 급락 이격 + 상대 거래량 0.5~4x | 7 | 60분 | +3.7639% | +0.6121% | DESCRIPTIVE_ONLY |

따라서 장초반 관찰 레일은 무한히 늘리지 않고 세 개만 유지한다.

1. `IMMEDIATE_OPENING_PROBE`: 0~1분 즉시 후보
2. `CONFIRMED_RECURRENT_RANK`: 반복 Rank-1 + 완료 1분봉 방향 확인
3. `DISLOCATION_REBOUND`: 시장 또는 종목 급락 이격 후 과열되지 않은 거래량 반동

`5~20분이면 눌림목` 같은 시간 단독 정책은 근거가 없다. 반복 Rank와 완료봉 확인이 없는 5~20분 후보는 현재 자료에서 좋지 않았다.

## 실제 거래 Horizon과의 관계

100개 실제 거래의 일괄 대체 horizon 결과는 다음과 같다.

| 대체 관측 | N | 평균 | 중앙값 | PF |
|---|---:|---:|---:|---:|
| +5분 | 69 | +0.0539% | +0.0880% | 1.2077 |
| +15분 | 68 | -0.0174% | -0.1562% | 0.9637 |
| +30분 | 67 | -0.0446% | -0.0749% | 0.9485 |
| +60분 | 66 | +0.0711% | -0.3009% | 1.0803 |
| EOD | 39 | -0.4337% | -0.8928% | 0.6876 |

전체 거래를 무조건 오래 보유하는 정책은 부정적이다. 조건부 장초반 cohort의 적정 horizon과 일반 거래의 적정 horizon은 분리해야 한다.

정확 연결 사례 중 모나미 2026-07-10 거래는 실제 +0.473%, 5분 +6.762%, 15분 +21.129%였다. 이는 강한 조기청산 의심 사례다. 반면 2026-07-15 모나미는 실제 +8.066%로 잘 처리됐다. 같은 종목과 비슷한 시간대라도 exit 정책을 일률적으로 연장할 수 없다는 예다.

## 후일 재점화

후일 +5% 고점이 관측된 사례는 8건이었다.

- 6건: threshold 이전 후보군에서 재탐지되지 않음
- 1건: 급등 후 너무 늦게 재탐지
- 1건: 사전 재탐지됐지만 Commander가 risk 기준으로 거절

이 결과는 “며칠 보유”보다 `LATENT_REACTIVATION_WATCH`가 더 적합하다는 뜻이다. 다만 과거 source universe에는 종목 목록이 아니라 개수만 남은 날이 있어, 6건이 공급자 누락인지 Scanner 순위 실패인지 완전히 분리할 수 없다.

## 현재 증거 공백

Commander 승인 후 미실행은 35건이며, 그중 33건(94.29%)은 구체적인 NOOP 사유가 없다.

- 이 상태에서는 Monitor가 좋은 기회를 잘못 막았다고 확정할 수 없다.
- 반대로 Monitor가 올바르게 위험을 막았다고도 확정할 수 없다.
- 다음 live validation에서 반드시 `candidate -> monitor evaluation -> hard gate -> blocker -> intent` 계보를 같은 decision ID로 저장해야 한다.

또한 chart-fit과 macro-chart-fit은 양수·음수군 각각 3건만 있어 현재 결론에 사용할 수 없다.

## 우선순위

### 1. NOOP 사유 정합성

행동은 바꾸지 않고 승인 후 미실행의 실제 hard gate와 blocker를 같은 decision ID로 보존한다. 이것이 없으면 진입 시점 개선을 평가할 수 없다.

### 2. 세 조건부 레일의 prospective shadow

세 레일을 동시에 기록하되 서로 섞지 않는다. 각 레일에서 5m, 15m, 30m, 60m, EOD와 MFE/MAE를 유지한다.

### 3. 조건별 horizon 검증

일반 거래 horizon을 늘리지 않는다. `IMMEDIATE_OPENING_PROBE`, `CONFIRMED_RECURRENT_RANK`, `DISLOCATION_REBOUND`별로 적정 horizon을 비교한다.

### 4. 재점화 watch replay

초기 Scanner 흔적을 D+5까지 observer watch에 남기고, 재등장 시 새 거래 신호로 평가한다. 기존 포지션 유지와 분리한다.

### 5. 행동 패치 한 개 선택

위 네 증거가 채워진 뒤 다음 중 하나만 선택한다.

- 장초반 소량 probe
- 반복 Rank 확인 후 진입 허용
- 승인 후 Monitor gate 조정
- 재점화 watch의 후보 공급자 연결

## 생성 산출물

- `reports/evaluation/offline_alpha/conditional_alpha_diagnosis/conditional_alpha_diagnosis.md`
- `conditional_alpha_episode_contexts.json`
- `conditional_stage_attribution.json`
- `conditional_horizon_report.json`
- `conditional_contrast_report.json`
- `reactivation_lineage.json`
- `reactivation_watch_replay.json`

모든 산출물은 offline research 또는 diagnostic only이며 주문을 생성하지 않는다.
