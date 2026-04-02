# Scanner Liquidity vs Volume Tuning Note

## 목적

이 문서는 scanner가 `trading_value`를 `volume_surge`보다 더 강하게 보는 현재 구조가
대형 유동성 종목 쏠림을 만들 수 있다는 관찰을 정리하고,
향후 어느 시점에 어떤 방식으로 조정하는 것이 안전한지 메모하기 위한 보조 문서다.

이 문서는 로드맵 원문을 대체하지 않는다.
또한 현재 monitor scoring shadow 검증을 방해하지 않기 위해,
지금 당장 튜닝을 적용하자는 제안이 아니라 "후속 후보와 적용 시점"을 정리하는 note다.

## 현재 관찰

현재 scanner 기본 score weight는 아래와 같다.

- `trading_value = 0.20`
- `volume_surge = 0.14`

관련 코드:

- `graphs/nodes/scanner_node.py:981`
- `graphs/nodes/scanner_node.py:984`

추가로 아래 완화/우대가 붙는다.

- `liquidity` priority가 있으면 `trading_value * 1.10`
- `volume_surge` priority가 있으면 `volume_surge * 1.08`
- `defensive` playbook이면 `trading_value * 1.08`

관련 코드:

- `graphs/nodes/scanner_node.py:1326`
- `graphs/nodes/scanner_node.py:1340`
- `graphs/nodes/scanner_node.py:1355`

즉 현재 구조는 자연스럽게 아래 방향을 만든다.

- 대형 유동성 종목 우대
- `top_value` / `liquidity` 소스 우대
- `defensive` playbook에서 거래대금 우대 강화

이 구조는 시장 리더 포착에는 유리하지만,
체감상 `005930`, `000660` 같은 대형 유동성 종목 쏠림을 강화할 수 있다.

## 방향성 판단

질문: `trading_value > volume_surge`를 조정하는 것이 지금 가려는 방향에 맞는가?

답: "가설 자체는 맞다. 하지만 지금 즉시 적용하는 것은 시점상 맞지 않다."

이유:

1. 현재 최우선 검증은 `5-1-2 Monitor Scoring Shadow`다.
2. 이 시점에 scanner weight를 같이 바꾸면 shadow vs legacy 차이의 원인 분리가 어려워진다.
3. 현재 문제는 "가설 부재"가 아니라 "적용 타이밍" 문제에 더 가깝다.

즉 이 튜닝은 혼란을 만드는 방향이 아니라,
"지금 바로 넣으면 혼란을 만들 수 있는 올바른 후속 후보"다.

## 비교할 두 가지 수정안

### 안 A. 전역 최소 수정

`trading_value`와 `volume_surge`의 기본 weight 우선순위를 뒤집는다.

예시:

- `trading_value 0.20 -> 0.14`
- `volume_surge 0.14 -> 0.20`

장점:

- 구현이 가장 단순하다
- 효과가 빠르고 명확하다

단점:

- 모든 playbook과 모든 장세에 동시에 적용된다
- 현재 문제 맥락이 `defensive + liquidity` 조합에 더 가까운 상황에서,
  영향 범위가 넓다
- shadow 검증 이후에도 원인 분리가 어려워질 수 있다

판단:

- 더 단순하지만 더 넓게 흔든다
- 안전성 기준에서는 차선책이다

### 안 B. defensive playbook 한정 완화

기본 weight는 유지하고,
`defensive` playbook에서만 `trading_value` 우대를 줄이거나
`volume_surge` 우대를 상대적으로 높인다.

예시 방향:

- `defensive`에서만 `trading_value` multiplier 완화
- 또는 `defensive`에서만 `volume_surge` multiplier 보강

현재 관련 코드:

- `graphs/nodes/scanner_node.py:1355`

장점:

- 현재 관찰된 문제 맥락에 더 직접적이다
- 다른 playbook을 덜 건드린다
- 영향 반경이 작아서 회귀 위험이 낮다

단점:

- 전역 weight 교체보다 해석 포인트가 조금 더 생긴다

판단:

- 현재 기준에서는 안 B가 더 안전하다
- "대형 유동성 쏠림 완화"와 "기존 구조 보존"의 균형이 더 좋다

## 권장 시점

### 지금 하지 말 것

아래가 끝나기 전에는 적용하지 않는 것을 권장한다.

- `5-1-2 Monitor Scoring Shadow` 장중 검증 종료
- shadow -> enabled 전환 여부 1차 결론 정리

이유:

- 지금 scanner weight를 건드리면
  monitor scoring shadow 결과 해석이 함께 흔들린다
- `legacy vs scoring` 차이가 monitor 때문인지
  scanner 후보 분포 변화 때문인지 분리하기 어려워진다

### 권장 적용 시점

가장 자연스러운 시점은 아래 둘 중 하나다.

1. `5-1-2` shadow 검증을 닫고, enabled 전환 결론을 낸 직후
2. `5-2` UI/reporting 구조 분리 작업과는 별개로, 별도 런타임 튜닝 턴에서 수행

즉 이 튜닝은 `5-2`의 일부가 아니라,
"shadow 검증 종료 후 수행하는 scanner local tuning"으로 다루는 것이 맞다.

## 5-3와의 관계

이 이슈는 `5-3 정책 구조화`와 직접 동일한 주제는 아니다.

이유:

- 이 문서는 strategist/commander policy ownership을 바꾸자는 문서가 아니다
- scanner local ranking weight의 방향을 어떻게 미세 조정할지에 대한 문서다

다만 아래 이유로 `5-3`과 충돌하지 않게 운영해야 한다.

- `5-3`에서는 policy ownership을 strategist/commander 쪽으로 정리할 가능성이 있다
- 따라서 현재 단계의 scanner tuning은
  "local quantitative ranking adjustment" 수준을 넘지 않아야 한다
- strategist schema나 policy object를 새로 도입하는 방식으로 확장하지 않는다

정리:

- 이 튜닝은 `5-3` 이전에도 가능하다
- 하지만 `5-1-2` shadow 검증을 닫기 전에는 비권장이다
- 구현한다면 "scanner local tuning"으로 작게 수행해야 한다

## 추천 결론

현재 기준 추천은 아래와 같다.

1. 지금은 적용하지 않는다
2. shadow -> enabled 판단을 먼저 닫는다
3. 그 다음 scanner 쏠림이 계속 보이면 안 B부터 검토한다

한 줄 요약:

`trading_value > volume_surge` 조정 가설 자체는 현재 방향과 맞지만,
지금 즉시 넣으면 shadow 검증 해석을 흐릴 수 있다.
후속 조정이 필요하다면 전역 weight 교체보다
`defensive` playbook 한정 완화가 더 안전하다.
