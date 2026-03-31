# SALT Monitor 진입 판단 개선 설계 문서 (5-1-2)

## 문서 목적
이 문서는 SALT(Soul Trader) 자동매매 시스템의 **Monitor 진입 판단 구조**를 최소 수정으로 개선하기 위한 설계 초안이다.

이번 단계의 목표는 기존의 과도한 hard-filter 누적 구조를 완전히 갈아엎는 것이 아니라,
기존 구조를 최대한 유지하면서도 **no-trade 과잉**을 줄일 수 있도록
**필수조건 + 점수 기반 보조 판단** 구조를 도입하는 방향을 정의하는 것이다.

이 문서는 `docs/roadmap/` 아래에 저장되는 설계 문서로 사용한다.

---

## 1. 배경과 문제 정의

현재 SALT는 다음 흐름으로 동작한다.

- 지휘자(Commander): 사이클 오케스트레이션
- 전략가(Strategist): 시장 맥락과 전략 방향 제시
- 스캐너(Scanner): 후보 종목 수집/정량화/랭킹
- 모니터(Monitor): 진입 타이밍 판단 및 intent 생성
- 감독관(Supervisor): 승인/정책 검증
- 수행자(Executor): 승인된 intent 실행
- 리포터(Reporter): 로그/리포트/사후 분석

시스템 아키텍처상 **에이전트는 intent까지만 만들고 실행은 가드 뒤에서 일어나야 한다**는 원칙은 그대로 유지한다. 이는 기존 설계의 핵심 안정성 원칙과도 일치한다. fileciteturn0file1

문제는 현재 **모니터의 진입 판단이 지나치게 보수적**이라는 점이다. 최근 장중 결과를 보면,
좋은 후보가 스캐너를 통과한 뒤에도 모니터에서 다음과 같은 이유로 반복적으로 진입이 차단된다.

- VWAP reclaim 미성숙
- volume ratio 부족
- breakout 미성숙
- confidence 소폭 부족
- pullback / reclaim / breakout / volume 조건의 누적 실패

그 결과,

1. 전략가가 방향을 고르고
2. 스캐너가 후보를 압축하고
3. 모니터가 다시 동일 성격의 필터를 강하게 적용하면서

실질적으로 **세 단계에서 모두 필터링이 중복**되고 있다.

즉 현재 문제는 단순히 조건이 많다는 것보다,
**조건들이 강한 차단 조건으로 누적되어 작은 미달도 전체 진입 실패로 이어지는 구조**에 가깝다.

---

## 2. 현행 구조 요약

현재 모니터 판단은 사실상 다음과 같은 hard-filter 조합에 가깝다.

```text
reclaim AND breakout AND pullback AND volume
```

혹은 최근 일부 개선 이후에도 본질적으로는 유사하다.

```text
reclaim AND (breakout OR (pullback AND volume))
```

이 구조는 완화된 것처럼 보이지만,
실전에서는 여전히 여러 조건이 동시에 충족되어야 하므로 다음 문제가 남는다.

### 2.1 현행 구조의 문제

- 작은 조건 미달이 전체 진입 불가로 이어진다.
- 시장이 먼저 움직이는 초기 구간을 놓치기 쉽다.
- 스캐너에서 이미 고른 종목을 모니터가 다시 과도하게 탈락시킨다.
- no-trade 비율이 높아지고, 거래 데이터 축적 속도가 느려진다.
- 이후 전략가/리포터가 학습하거나 조정할 수 있는 실거래 피드백도 줄어든다.

### 2.2 지금 당장 바꾸지 않을 것

이번 단계는 대공사가 아니다. 다음은 유지한다.

- 7에이전트 전체 구조
- approval / guard / execution 구조
- `reports/trades/` 저장 구조
- canonical artifact 기본 구조
- Supervisor / Executor 책임 분리
- 기존 DTO의 필수 필드

즉 이번 작업은 **모니터 진입 판단부의 중간급 패치**다.

---

## 3. 목표

이번 설계의 목표는 아래와 같다.

### 3.1 핵심 목표

- no-trade 과잉 완화
- 진입 판단을 더 유연하게 조정
- 전략가 / 스캐너 / 모니터 역할 중복 완화
- 기존 시스템 안정성 유지
- 최소 수정으로 점진적 적용 가능하게 설계

### 3.2 비목표

이번 단계에서 아래는 하지 않는다.

- 전략가 로직 전면 재설계
- 스캐너 로직 전면 재설계
- 승인/가드 체계 변경
- executor 동작 변경
- `reports/trades/` 구조 변경
- 대규모 LangGraph 오케스트레이션 변경

---

## 4. 제안 구조: Two-layer Decision Model

모니터 진입 판단을 2층으로 나눈다.

### 4.1 Layer 1: Hard Filters

정말 막아야 하는 최소 조건만 남긴다.

예시:

- 거래 불가능 수준의 유동성 부족
- 이상 급락/이상 체결 등 극단적 리스크 상태
- 필수 시세 데이터 부족 또는 freshness 실패

Hard filter의 목적은 **좋은 타이밍 선별**이 아니라,
**명백히 위험하거나 판단 불가능한 상황 차단**이다.

즉 기존의 reclaim, breakout, pullback, volume 같은 타이밍 요소는
가능한 한 hard filter에서 빼고 score 영역으로 이동한다.

### 4.2 Layer 2: Scoring

진입 관련 신호는 점수화한다.

예시:

- VWAP reclaim: +2
- breakout 구조 확인: +2
- pullback maturity: +1
- volume support: +1
- 전략가/뉴스/심리 정합성: +1

이 값은 초기 예시일 뿐이며,
실제 적용 시 최근 로그 기반으로 보정 가능해야 한다.

### 4.3 Entry Rule

예시:

```text
hard_filter_passed == true
AND total_score >= entry_threshold
```

예를 들면 threshold를 3으로 두고,
다음과 같이 진입 가능하게 한다.

- reclaim(+2) + volume(+1) = 3 → 진입 가능
- breakout(+2) + pullback(+1) = 3 → 진입 가능
- reclaim(+2) + breakout(+2) = 4 → 강한 진입

반대로 기존처럼 모든 조건을 동시에 강제하지 않는다.

---

## 5. 역할 분리 관점에서의 정리

기존 문제는 세 에이전트가 모두 필터를 수행하는 데 있었다.

### 5.1 전략가

전략가는 다음에 집중한다.

- 시장 맥락 해석
- playbook / 전술 방향 제시
- 어떤 유형의 종목/상황을 선호할지 제안

전략가는 구체적 진입 타이밍을 강하게 확정하지 않는다.

### 5.2 스캐너

스캐너는 다음에 집중한다.

- 후보 종목 수집
- 거래대금 / 변동성 / 구조 / 테마 / 정량 특징 계산
- 상대적 랭킹

스캐너는 **후보 압축**이 목적이지,
최종 진입 타이밍 판정자가 아니다.

### 5.3 모니터

모니터는 다음에 집중한다.

- 실시간/준실시간 타이밍 판단
- 점수 기반 진입 결정
- intent 생성

즉 **최종 진입 판단자는 모니터 하나**가 되도록 역할을 더 선명하게 가져간다.

---

## 6. 최소 수정 원칙

이번 단계는 코드 수정 범위를 넓히지 않는 것이 중요하다.

우선순위는 다음과 같다.

### 6.1 우선 수정 대상

- `libs/runtime/intraday_monitor_signals.py`
- `graphs/nodes/monitor_node.py`
- 관련 monitor 테스트 파일

### 6.2 가능하면 유지할 것

- 전략가 출력 구조
- 스캐너 출력 구조
- canonical artifact 상위 구조
- reporter 파이프라인 기본 경로

### 6.3 Additive 변경 원칙

DTO/IO 계약은 additive로 확장해야 하며,
기존 필수 필드는 제거하지 않는다. 이는 현재 프로젝트의 계약 안정성 원칙과도 일치한다. fileciteturn0file2

즉 monitor output에 필요한 필드를 추가하더라도,
기존 필드는 유지해야 한다.

---

## 7. 데이터 계약 영향

### 7.1 추가 권장 필드

monitor output 또는 canonical monitor artifact에 다음 필드를 추가한다.

- `hard_filter_passed: bool`
- `hard_filter_fail_reasons: list[str]`
- `total_score: float | int`
- `score_breakdown: dict[str, float | int]`
- `entry_threshold: float | int`
- `score_decision_reason: str`

### 7.2 유지해야 할 것

- 기존 `decision_phase`, `action`, `status`
- 기존 threshold snapshot
- 기존 signal snapshot
- 기존 blocker / reason code
- 기존 decision_trace 계열

### 7.3 호환성 원칙

breaking change 금지.

- required field 제거 금지
- 의미 변경 금지
- 새 의미는 새 필드로 추가

이는 전체 프로젝트의 안정성 규칙과 맞춰야 한다. fileciteturn0file2

---

## 8. 로깅 / 관측성 설계

이 작업은 단순히 진입을 늘리는 것이 아니라,
왜 진입했는지 혹은 왜 못했는지 더 잘 보이게 해야 한다.

프로젝트의 관측성 목표는 모든 run이 `run_id`로 추적 가능하고,
승인/가드/판단 이유가 기록되는 것이다. fileciteturn0file3

따라서 다음 이벤트를 권장한다.

### 8.1 신규/확장 이벤트

- `monitor.hard_filter_failed`
- `monitor.score_computed`
- `monitor.entry_decision`

### 8.2 event payload 예시

- `run_id`
- `symbol`
- `hard_filter_passed`
- `hard_filter_fail_reasons`
- `score_breakdown`
- `total_score`
- `entry_threshold`
- `decision`
- `primary_reason_code`

### 8.3 기대 효과

- 장중 “왜 안 샀는가”를 더 쉽게 설명 가능
- 기존 blocker 통계와 score 통계를 함께 비교 가능
- shadow mode에서 기존 로직과 신규 로직 차이 비교 가능

---

## 9. fallback 및 feature flag

최소 수정 원칙상, 기존 로직을 바로 제거하지 않는다.

### 9.1 추천 플래그

예시:

- `MONITOR_SCORING_ENABLED`
- `MONITOR_SCORING_SHADOW_MODE`
- `MONITOR_ENTRY_SCORE_THRESHOLD`

### 9.2 동작 원칙

#### case 1. scoring disabled
기존 monitor 판단 유지

#### case 2. shadow mode enabled
기존 판단은 그대로 사용하되,
신규 scoring 결과를 로그/아티팩트에 함께 기록

#### case 3. scoring enabled
hard-filter + score 판단을 primary로 사용
기존 hard-threshold 구조는 fallback 또는 비교 기준으로 유지

---

## 10. 단계별 적용 계획

### Phase 5-1-2
설계 문서 작성

- 판단 철학 정리
- additive 필드 정의
- 로깅 설계 정의

### Phase 5-2
최소 구현

- intraday monitor signal 계산부에 score 계산 추가
- monitor node에서 score 결과 기록
- feature flag로 활성화 여부 제어

### Phase 5-2.5
shadow 검증

- 장중 또는 장후 replay에서 기존 판단 vs score 판단 비교
- no-trade 감소 여부 확인
- 과매수/오진입 급증 여부 확인

### Phase 5-3
primary 전환 검토

- shadow 결과가 안정적이면 scoring primary 적용
- 기존 로직은 fallback으로 유지

---

## 11. 기대 효과

### 11.1 직접 효과

- no-trade 비율 감소
- 기회 손실 완화
- 시장 초반 움직임 포착 가능성 증가

### 11.2 구조 효과

- 전략가/스캐너/모니터 역할 중복 완화
- 모니터를 최종 타이밍 판단자로 더 명확히 정의
- 향후 threshold 튜닝보다 score 튜닝이 쉬워짐

### 11.3 운영 효과

- operator brief / trade story에 설명 가능한 근거 증가
- score breakdown 기반 디버깅 가능
- 종목별 반복 blocker 패턴과 함께 비교 분석 가능

---

## 12. 리스크와 대응

### 12.1 리스크

- 진입 건수만 늘고 품질이 나빠질 수 있음
- score 설계가 애매하면 기존보다 설명이 어려워질 수 있음
- threshold가 너무 낮으면 잡음 거래 증가 가능

### 12.2 대응

- shadow mode 먼저 적용
- 기존 blocker 로깅 유지
- score breakdown을 반드시 남김
- threshold를 보수적으로 시작
- 전략가/스캐너는 건드리지 않고 monitor만 먼저 조정

---

## 13. 결론

이번 변경은 SALT 전체 철학을 바꾸는 대공사가 아니다.

핵심은 다음 한 줄로 정리된다.

> 기존의 “여러 조건을 모두 만족해야 진입” 구조를,
> “위험한 상황만 hard-filter로 막고 나머지는 점수 합산으로 판단” 구조로 최소 수정 전환한다.

이 접근은 현재 시스템의 안정성 원칙,
즉 **에이전트는 intent까지만 만들고 실행은 가드 뒤에서 일어나야 한다**는 구조를 건드리지 않으면서도, fileciteturn0file1
실전에서 가장 큰 문제인 **과도한 no-trade**를 완화할 수 있는 현실적인 다음 단계다.

---

## 14. 후속 Codex 작업 원칙

후속 구현 프롬프트에서는 아래 원칙을 지켜야 한다.

1. 수정 범위 최소화
2. additive 변경만 수행
3. 기존 필드/리포트 경로 유지
4. feature flag 기반 적용
5. shadow mode 우선 지원
6. 테스트 보강 포함

이 원칙을 지키면 5-2 구현은 “대공사”가 아니라,
**monitor 진입 판단부 중심의 중간급 패치**로 관리 가능하다.
