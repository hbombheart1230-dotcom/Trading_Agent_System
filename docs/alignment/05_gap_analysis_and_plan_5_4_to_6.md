# 05. Gap Analysis and Plan: Phase 5-4 to Phase 6

## 1. 목적

이 문서는 현재 구조와 목표 구조의 차이를 정리하고, 5-3-2 이후 5-4와 Phase 6에서 무엇을 정리해야 하는지 명확히 한다.

핵심은 다음 한 줄이다.

> **지금은 logic expansion보다 ownership and wiring 정리가 먼저다.**

---

## 2. 현재와 목표의 가장 큰 차이

## 2.1 Commander
### 현재
- orchestration owner
- selected/applied policy provenance owner
- route/path owner

### 목표
- market operating posture owner
- strategist invocation owner
- policy apply owner
- no-trade posture owner

즉 Commander는 단순 라우터에서 “상위 지휘 체계의 owner”로 더 명시되어야 한다.

---

## 2.2 Strategist
### 현재
- market frame producer
- playbook producer
- policy producer
- 일부 상위 판단 역할까지 함께 수행하는 느낌

### 목표
- policy proposal owner
- strategy implementation owner
- Commander가 준 상위 방향을 구체화하는 참모 역할

즉 Strategist는 약해지는 것이 아니라 **더 명확해진다**.  
상위 지휘 ownership과 정책 proposal ownership이 분리되는 것이다.

---

## 2.3 Monitor
### 현재
- policy-aware consumer readiness 확보
- evidence / trace / summary surface 확보
- final BUY/WAIT safety owner는 아직 legacy gate 비중이 큼

### 목표
- applied policy를 더 직접적으로 소비하는 consumer
- policy-aware decision 비중 확대
- legacy gate는 fallback safety로 점진 하향

Monitor는 방향성보다 migration sequencing이 중요하다.

---

## 2.4 Reporter
### 현재
- 매우 중요한 post-run 해석 계층
- 그러나 단일 node라기보다 subsystem 성격
- UI/read model/report pipeline 경계가 완전히 정리되지는 않음

### 목표
- runtime과 post-run의 경계 명확화
- intraday / trade / daily report 구조 정리
- strategy feedback loop의 공식 owner surface 마련

---

## 3. 5-4의 정확한 의미

5-4는 decision-expansion phase가 아니다.  
핵심은 **ownership and wiring design**이다.

### 3.1 Strategist의 위치
- interpretation_policy / threshold_policy proposal producer

### 3.2 Commander의 위치
- selected source 결정
- selected policy / applied policy 확정
- provenance 고정

### 3.3 Monitor의 위치
- selected/applied policy consumer
- signal evidence consumer
- chart-structure feature를 포함한 해석 계층 consumer

### 3.4 legacy gate의 위치
- 여전히 final fallback safety
- 당장 제거 대상 아님

즉 5-4는 “누가 만들고 누가 확정하고 누가 소비하는가”를 확실히 하는 단계다.

---

## 4. 5-4에서 꼭 문서로 못 박아야 할 것

## 4.1 applied policy source chain
무엇이 proposal이고 무엇이 official applied인지 명확해야 한다.

## 4.2 route ownership
full-cycle, cached strategist, monitor 중심 경로 등 route 결정 ownership을 Commander로 명확히 한다.

## 4.3 no-trade posture ownership
시장 상황상 거래를 자제하는 posture가 누구의 owner인지 분명해야 한다.  
이것이 계속 Strategist/Commander 사이에서 흔들리면 설계가 꼬인다.

## 4.4 policy consumer surface
Monitor가 어떤 contract surface를 1순위로 읽는지 고정해야 한다.

---

## 5. Phase 6의 정확한 의미

Phase 6은 production-grade agent system으로 가는 정리 단계다.

### 5.1 orchestration
- state-based transition
- retry / cancel / transition policy

### 5.2 reporting
- intraday / trade / daily report 구조 정리
- reporting read layer 정리
- strategist feedback surface 정리

### 5.3 settings / policy
- env-heavy runtime에서 policy-centric runtime으로 이동

### 5.4 observability
- metrics
- alerts
- audit log
- operator-facing health summary

즉 6은 “운영 가능한 시스템”으로 완성하는 단계다.

---

## 6. Reporter를 6에서 어떻게 볼 것인가

이 부분은 지금 반드시 문서상으로 결정하는 게 좋다.

### 옵션 A. Reporter를 subsystem으로 공식화
장점:
- 현재 구조와 가장 잘 맞음
- operator brief / trade report / daily report / strategy memory를 자연스럽게 묶을 수 있음

단점:
- 에이전트로서의 일관된 체감은 줄어들 수 있음

### 옵션 B. Reporter를 하나의 orchestrated node로 재구성
장점:
- 7-agent mental model이 더 단순해짐

단점:
- 현재 분산된 report pipeline을 많이 건드려야 함

현재 상태에 가장 정직한 선택은 옵션 A에 가깝다.

---

## 7. 우선순위 제안

### 1순위: 5-4 ownership 문서화
- Commander / Strategist / Monitor / legacy gate 역할 고정

### 2순위: 장중 평가로 evidence 수집
- 실제 block reason, selected/apply policy 흐름, intent lifecycle 확인

### 3순위: 5-4 wiring 반영
- proposal → applied → consumer 구조 강화

### 4순위: Phase 6 reporting/read-model 정리
- Reporter subsystem 경계 확정
- 전략 피드백 루프 연결

---

## 8. 최종 정리

현재 시스템은 “많이 부족한 상태”가 아니라 아래처럼 보는 것이 더 정확하다.

- lifecycle은 이미 상당히 성숙하다
- policy-aware Monitor foundation도 생겼다
- canonical artifact 중심 관측 체계도 만들어졌다
- 이제 필요한 것은 더 많은 로직이 아니라 ownership과 wiring 정리다

따라서 다음 단계의 핵심 질문은 이것이다.

1. Commander는 어디까지 owner인가
2. Strategist는 proposal owner로 어떻게 정리할 것인가
3. Monitor는 어떤 applied policy surface를 1순위로 소비할 것인가
4. Reporter는 agent인가 subsystem인가

이 네 질문에 대한 답이 5-4와 6의 설계 품질을 결정한다.
