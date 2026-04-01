# Chart Structure Feature Candidates

## 1. 목적

- 현재 monitor는 `VWAP / trend_strength / breakout / pullback / volume ratio / prior_bar_low / peak_drawdown` 같은 압축된 feature를 기준으로 분봉 차트를 판단한다.
- 이 구조는 충분히 실용적이지만, 사람이 차트에서 직접 읽는 `추세선 / 크로스 / 지지저항 / 안착` 개념을 명시적으로 모델링하지는 않는다.
- 이 문서는 향후 적용 가능한 차트형 feature 후보를 정리하기 위한 메모다.
- 현재 문서는 구현 지시가 아니라 후보 정의 문서이며, policy ownership을 재정의하지 않는다.

한 줄 요약:

현재 시스템은 “차트를 feature로 압축해서 보는 구조”이고, 이 문서는 “차트 구조 인식 계층을 보강하기 위한 후보 목록”이다.

## 2. 현재 구조 요약

현재 monitor가 실제로 보는 것:

- VWAP distance / VWAP reclaim
- breakout / breakout gap
- pullback depth / pullback maturity
- volume ratio / volume readiness
- trend_strength
- prior_bar_low
- peak_drawdown

핵심 특징:

- 1분봉 기반 판단
- latest snapshot 중심 계산
- 파생 feature 기반 decision
- 차트 드로잉 기반 구조 인식은 없음

실무 해석:

- 현재 구조는 “차트 전체를 그려서 읽는 방식”이 아니라, 차트에서 중요한 상태를 수치화한 feature를 조합하는 방식이다.
- 따라서 현재 구조를 유지하면서도, 차트형 feature를 additive하게 보강하는 방향이 자연스럽다.

## 3. 부족한 차트형 정보

### 3.1 Moving Average / Cross 구조

예시:

- `MA5 > MA20` 또는 `MA5 < MA20`
- VWAP 재돌파 이후 `MA5` 재하회
- `MA5-MA20` 간격 확장 / 수축
- `MA20` 기울기 전환

설명:

- 현재는 `ma20_gap` 계열 feature가 일부 존재하지만, 실제 entry/exit rule로 직접 쓰이지 않는다.
- 사람은 “이평 정배열 유지”, “단기 이평 이탈”, “재돌파 후 이평 재이탈”을 차트 해석에 많이 사용한다.

보강 포인트:

- 단순 gap 값보다 `cross state + 유지 시간 + 기울기`를 함께 보는 구조가 필요하다.

### 3.2 Support / Resistance (스윙 구조)

예시:

- 최근 `N`봉 swing low / swing high
- intraday box range 상단 / 하단
- 2회 이상 터치된 지지선 / 저항선
- 최근 돌파 level 재지지 여부

설명:

- 현재는 `prior_bar_low` 정도만 쓰고 있어서 “직전 저점 이탈”은 보지만, 구조적 지지/저항은 보지 않는다.
- 사람이 보는 “이 자리가 박스 하단인지”, “방금 돌파한 자리를 다시 지지하는지” 같은 판단은 아직 약하다.

보강 포인트:

- 단일 봉 low/high 대신 `최근 구간의 구조적 level`을 계산해두면 entry와 exit 설명력이 좋아질 수 있다.

### 3.3 Trendline / Channel 구조

예시:

- 상승 추세선 유지
- 하향 추세선 돌파
- regression 기반 channel 상단/하단
- 상승 채널 하단 이탈

설명:

- 현재는 `trend_strength`가 추세를 압축해서 보여주지만, 실제 “선 기반 구조”는 없다.
- 사람이 차트를 볼 때는 “추세가 살아 있는가”, “채널이 무너졌는가”를 시각적으로 해석하는 경우가 많다.

보강 포인트:

- 추세선 자체를 복잡하게 그리기보다, `최근 N봉 회귀선 기울기`, `회귀 채널 하단 거리`처럼 계산 가능한 형태가 더 안전하다.

### 3.4 Multi-bar Confirmation (연속성)

예시:

- VWAP 위 2~3봉 유지
- breakout 후 재지지 2봉 확인
- higher low / lower high 연속 패턴
- 2봉 연속 거래량 회복

설명:

- 현재는 snapshot 중심이라 “지금 순간 조건이 맞는가”는 잘 보지만, “몇 봉 연속으로 안착했는가”는 약하다.
- 사람이 보는 차트 판단에서는 연속성, 안착, 실패 후 재도전 여부가 중요하다.

보강 포인트:

- 단일 tick/봉의 false positive를 줄이고 confirmed entry / confirmed exit 품질을 높이는 데 유용하다.

## 4. Entry 후보 feature

### VWAP 재안착 (2~3봉 유지)

설명:

- 가격이 VWAP를 회복한 뒤 2~3개 봉 동안 VWAP 위에서 유지되는지 보는 feature.

계산 방법:

- 최근 3개 봉의 `close > vwap` 여부를 계산한다.
- `vwap_hold_count` 또는 `vwap_reclaim_persistence`로 표현한다.
- 예: 최근 3봉 중 2봉 이상이 `close >= vwap`이면 partial pass, 3봉 모두면 strong pass.

기대 효과:

- 순간 reclaim과 실제 안착을 구분할 수 있다.
- reclaim 이후 fake breakout 진입을 줄이는 데 유용하다.

우선순위:

- `HIGH`

### MA cross + 유지 여부

설명:

- 단기 이평이 중기 이평을 상향 돌파했는지, 그리고 그 상태가 몇 봉 유지되는지 보는 feature.

계산 방법:

- `ma5`, `ma20` 계산
- `ma5 > ma20` 여부
- 최근 2~3봉 동안 그 상태가 유지되었는지 `ma_cross_persistence`로 계산
- 추가로 `ma5-ma20` gap의 증가 여부도 함께 본다.

기대 효과:

- breakout 직후 추세 유지 여부를 더 명확히 볼 수 있다.
- “재돌파 후 바로 무너지는” 진입을 줄이는 데 도움이 된다.

우선순위:

- `HIGH`

### Recent high 대비 위치 (late entry 방지)

설명:

- 현재 가격이 최근 `N`봉 high를 얼마나 초과했는지 보고 late chase를 막는 feature.

계산 방법:

- `recent_high_gap_pct = (current_price / recent_high) - 1`
- `recent_high_gap_pct`가 너무 크면 late entry risk로 본다.
- threshold는 policy가 아니라 feature 값만 계산한다.

기대 효과:

- breakout은 맞지만 이미 너무 멀리 간 진입을 구분할 수 있다.
- “막 돌파한 자리”와 “이미 과열된 자리”를 나눌 수 있다.

우선순위:

- `HIGH`

### Volume expansion 지속성

설명:

- volume ratio가 한 순간만 튄 것이 아니라 2~3봉 연속으로 유지되는지 보는 feature.

계산 방법:

- 최근 3봉의 `volume / avg_volume` 비율 계산
- `volume_ratio_persistence`
- `volume_expansion_streak`

기대 효과:

- volume confirmation의 신뢰도를 높일 수 있다.
- 단발성 거래량 왜곡을 줄이는 데 유리하다.

우선순위:

- `HIGH`

### Swing low above VWAP

설명:

- 최근 swing low가 VWAP 위에서 형성되는지 보는 feature.

계산 방법:

- 최근 `N`봉에서 local low 후보를 찾고
- 그 low가 VWAP 위인지, 또는 VWAP 근처에서 지지받는지 확인한다.

기대 효과:

- reclaim 이후 지지가 실제로 만들어졌는지 판단할 수 있다.
- 단순 reclaim보다 구조적 품질을 더 볼 수 있다.

우선순위:

- `MID`

### Box breakout retest hold

설명:

- 박스권 상단을 돌파한 뒤, 그 level을 다시 지지하고 있는지 보는 feature.

계산 방법:

- 최근 `N`봉 range 상단 계산
- 현재가가 상단 위에 있고, 최근 1~2봉 저가가 상단을 크게 깨지 않았는지 확인

기대 효과:

- breakout 후 재지지 구조를 모델링할 수 있다.
- 인간이 보는 “돌파 후 눌림 확인”에 가깝다.

우선순위:

- `MID`

### Higher low continuation

설명:

- 최근 swing low들이 점진적으로 높아지는지 보는 feature.

계산 방법:

- 최근 3개 local low를 찾고 `low1 < low2 < low3`인지 계산
- 엄격한 boolean 대신 slope/quality score로 표현 가능

기대 효과:

- 추세 지속형 pullback entry의 질을 더 잘 구분할 수 있다.

우선순위:

- `MID`

## 5. Exit 후보 feature

### MA 하향 크로스 기반 exit

설명:

- 단기 이평이 중기 이평을 하향 이탈하고, 그 상태가 1~2봉 유지되는지 보는 exit feature.

계산 방법:

- `ma5 < ma20`
- 최근 2봉 연속 유지 여부
- 필요하면 가격이 VWAP 아래인지 함께 기록

기대 효과:

- trend breakdown을 더 차트형 구조로 설명할 수 있다.
- 단순 noise 하락과 구조 이탈을 구분하는 데 도움된다.

우선순위:

- `HIGH`

### Swing low 이탈

설명:

- 최근 의미 있는 swing low를 하향 이탈했는지 보는 feature.

계산 방법:

- 최근 `N`봉에서 local low를 구하고
- 현재가가 해당 low 아래로 내려갔는지 계산

기대 효과:

- 현재의 `prior_bar_low`보다 더 구조적인 지지선 붕괴 판단이 가능하다.

우선순위:

- `HIGH`

### Channel 하단 이탈

설명:

- 최근 구간의 상승 채널 또는 회귀 채널 하단을 이탈했는지 보는 feature.

계산 방법:

- 최근 `N`봉 회귀선과 표준편차 밴드 또는 단순 channel lower band 계산
- 현재가가 channel lower band 아래인지 확인

기대 효과:

- “추세는 있었지만 채널이 무너졌다”는 판단을 분리할 수 있다.

우선순위:

- `MID`

### 구조 붕괴 후 재반등 실패

설명:

- 한번 구조가 깨진 뒤 반등 시도는 있었지만 이전 지지/저항을 회복하지 못한 경우를 exit feature로 본다.

계산 방법:

- 구조 붕괴 발생 이후 최근 1~2봉 반등 고가가 이전 붕괴 level을 회복하지 못했는지 계산
- `failed_reclaim_after_break` 형태의 feature로 표현

기대 효과:

- “한 번 깨진 뒤 되돌림 실패”를 잡아낼 수 있다.
- 사람이 차트에서 느끼는 “약한 반등”을 정량화할 수 있다.

우선순위:

- `MID`

### VWAP 재이탈 지속성

설명:

- VWAP 하향 이탈이 단발인지, 2~3봉 지속인지 보는 feature.

계산 방법:

- 최근 3봉 중 `close < vwap` 개수
- `vwap_breakdown_persistence`

기대 효과:

- 현재 `vwap_breakdown`을 더 안정적으로 보강할 수 있다.

우선순위:

- `HIGH`

### Lower high failure after peak

설명:

- 고점을 찍은 뒤 반등 고점이 점점 낮아지는지 보는 exit feature.

계산 방법:

- 최근 2~3개 local high 비교
- `high1 > high2 > high3` 또는 lower-high count 계산

기대 효과:

- peak drawdown과 함께 쓰면 “고점 후 구조 약화”를 더 잘 설명할 수 있다.

우선순위:

- `MID`

## 6. 지금 당장 넣지 말아야 할 것

- 복잡한 추세선 피팅
  - 이유: intraday noise에 과적합될 가능성이 높다.
- 너무 많은 보조지표 직접 도입
  - 예: RSI, MACD, Bollinger를 동시에 다 넣는 방식
  - 이유: feature 중복과 설명력 저하 위험이 있다.
- strategist/commander 정책 의미까지 monitor feature 안에서 해석하는 구조
  - 이유: 향후 policy ownership 단계와 충돌할 수 있다.
- 시각적 패턴을 과하게 규칙화한 candle pattern 집합
  - 이유: 규칙 폭증과 false positive 증가 가능성이 높다.

## 7. Phase 5-3 연결 메모

- 현재 feature는 monitor 내부 local logic으로만 존재한다.
- 향후에는 `Strategist -> policy object -> Monitor` 구조로 ownership이 이동할 수 있다.
- 따라서 지금 단계에서는 feature 후보를 정의할 수는 있지만, 그 feature의 정책 의미까지 먼저 고정하면 안 된다.
- 예를 들어 `VWAP 재안착 3봉 유지`는 feature로 정의할 수 있지만, “반드시 3봉이어야 한다” 같은 policy 수준 결정은 5-3 이후 ownership 정리와 함께 다루는 편이 안전하다.
- 이 문서는 policy 문서가 아니라 feature candidate 목록 문서다.
- 구현 착수 시점은 `Phase 5-3 이후`를 기본 권장으로 둔다.
- 이유는 이 feature들이 단순 계산 추가를 넘어서, 최종적으로는 “누가 이 의미를 소유하고 threshold/usage를 결정하는가”와 연결되기 때문이다.
- 따라서 현재 단계에서는 후보 정의와 우선순위 정리까지만 수행하고, 실제 코딩/활성화는 5-3의 policy ownership 정리 이후에 검토하는 것이 바람직하다.

## 8. 핵심 요약

- 현재 monitor는 분봉 기반 차트를 실제로 보고 있지만, 차트를 feature로 압축해서 읽는 구조다.
- 향후 보강 후보는 `MA/Cross`, `지지저항`, `추세선/채널`, `다중 봉 안착` 계열이 가장 자연스럽다.
- 우선순위는 `VWAP 재안착 지속성`, `MA cross + 유지`, `late entry 방지`, `volume expansion 지속성`, `swing low 이탈`, `VWAP 재이탈 지속성` 쪽이 높다.
- 복잡한 차트 드로잉이나 보조지표 남용은 초기에 피하는 것이 좋다.
