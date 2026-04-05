# 03. Agent Roles, Inputs, Outputs, and Handoffs

## 1. 목적

이 문서는 각 에이전트의 책임 경계를 구체적으로 정리한다.  
특히 “무엇을 받는가 / 무엇을 넘기는가 / 무엇을 하면 안 되는가 / 현재 어떤 ownership 문제를 안고 있는가”를 명확히 한다.

---

## 2. 전체 handoff 요약

현재 시스템의 기본 handoff는 아래와 같다.

```text
Commander
  → Strategist
  → Scanner
  → Monitor
  → Supervisor
  → Executor
  → Reporter
```

하지만 이 선형 도식만 보면 놓치기 쉬운 점이 있다.

- Commander는 단순히 첫 번째 노드가 아니라 route/provenance owner다.
- Strategist는 단순 조언자가 아니라 정책 proposal producer다.
- Reporter는 선형 runtime의 마지막 단계라기보다 post-run subsystem이다.

---

## 3. Commander

## 3.1 목적
- 런타임 흐름을 정리한다.
- 어떤 route를 탈지 결정한다.
- 어떤 policy source를 canonical applied policy로 볼지 provenance를 고정한다.

## 3.2 주요 입력
- runtime phase
- 현재 holding/flat 상태
- cached strategist context
- 기존 state의 policy 관련 surface
- 상위 runtime control / resilience context

## 3.3 주요 출력
- commander decision
- selected/applied policy와 provenance
- route/path 관련 runtime plan
- downstream이 소비할 commander context

## 3.4 현재 핵심 책임
- strategist를 다시 부를지 말지 결정하는 오케스트레이션
- selected source / applied policy 확정
- route와 provenance 기록

## 3.5 비책임
- 종목을 직접 고르지 않는다
- micro signal을 직접 계산하지 않는다
- OrderIntent를 만들지 않는다
- 주문을 실행하지 않는다

## 3.6 현재 상태 평가
현재 Commander는 “진짜 상위 지휘자”라기보다 다음 두 역할이 강하다.

- orchestration owner
- applied policy / provenance owner

5-4의 핵심은 여기에 operating posture ownership을 더 분명히 얹는 것이다.

---

## 4. Strategist

## 4.1 목적
- 시장/전략 frame을 만든다.
- 하위 agent가 읽을 수 있는 policy proposal을 만든다.

## 4.2 주요 입력
- commander context
- market/news/sentiment context
- recent strategy feedback
- candidate hints 또는 runtime market context

## 4.3 주요 출력
- strategist output
- strategy_policy
- monitor_policy / monitor entry related policy surface
- scanner guidance
- report focus / memory advisory surface

## 4.4 현재 핵심 책임
- playbook / themes / avoid_themes / scanner bias 제안
- downstream용 structured policy proposal 생성
- 전략 rationale과 frame 생성

## 4.5 비책임
- 최종 실행 decision owner가 아니다
- 직접 OrderIntent를 만들지 않는다
- execution을 하지 않는다

## 4.6 현재 상태 평가
현재 Strategist는 단순 참모보다 더 강한 역할을 가지고 있다.  
즉, 전략가이면서 정책 producer이기도 하다.

따라서 5-4 이후에는 다음처럼 정리하는 것이 자연스럽다.

- Commander: applied policy owner
- Strategist: policy proposal owner

---

## 5. Scanner

## 5.1 목적
- 전략 frame을 바탕으로 실제 감시 대상 종목을 선발한다.

## 5.2 주요 입력
- strategist output
- scanner guidance / scanner policy
- market feature / quote / intraday / sentiment context
- 후보군 구성에 필요한 시장 데이터

## 5.3 주요 출력
- selected
- top_stock
- ranked_candidates
- scanner_output
- candidate pool observability metadata

## 5.4 현재 핵심 책임
- 후보군 구성
- 점수화
- top candidate 선택
- selection basis와 ranked summary 기록

## 5.5 비책임
- entry/exit를 직접 판단하지 않는다
- OrderIntent를 만들지 않는다
- execution을 하지 않는다

## 5.6 현재 상태 평가
Scanner는 역할 경계가 비교적 건강하다.  
다만 여전히 다음 문제가 남아 있다.

- 잘 보이는 종목과
- 지금 Monitor가 들어갈 수 있는 종목이
항상 같지 않다.

즉 Scanner-Monitor alignment는 여전히 중요한 과제다.

---

## 6. Monitor

## 6.1 목적
- selected symbol을 감시하고 entry/exit intent를 만든다.

## 6.2 주요 입력
- selected symbol
- selected feature snapshot
- monitor 관련 policy surface
- signal evidence
- minute/intraday market data
- held position context

## 6.3 주요 출력
- OrderIntent
- monitor_output
- monitor_exit / entry 관련 observability surface
- policy interpretation / trace / summary

## 6.4 현재 핵심 책임
- selected symbol에 대한 signal evaluation
- policy-aware interpretation surface 생성
- evidence / trace / summary surface 기록
- 최종적으로 intent 생성

## 6.5 비책임
- policy source precedence를 정하지 않는다
- upstream policy를 만들지 않는다
- universe를 다시 스캔하지 않는다
- execution을 하지 않는다

## 6.6 현재 상태 평가
Monitor는 현재 설계 의도와 가장 잘 맞는 축이다.  
다만 final BUY/WAIT owner는 아직 legacy gate 쪽 비중이 남아 있으며, policy-driven ownership migration은 다음 단계 과제다.

---

## 7. Supervisor

## 7.1 목적
- OrderIntent를 승인/거절/수정한다.

## 7.2 주요 입력
- OrderIntent
- risk / approval 관련 정책
- strategy_policy_summary 등 관측용 메타 surface

## 7.3 주요 출력
- SupervisorDecision
- 승인/거절 이유
- 수정 내역(있다면)

## 7.4 현재 핵심 책임
- approval mode와 risk policy 적용
- execution 전 마지막 정책 통제

## 7.5 비책임
- 전략을 새로 만들지 않는다
- 종목을 다시 고르지 않는다
- 브로커를 직접 호출하지 않는다

---

## 8. Executor

## 8.1 목적
- 승인된 결정을 실제 broker call path로 연결한다.

## 8.2 주요 입력
- approved SupervisorDecision
- OrderIntent
- execution mode / guard 관련 설정

## 8.3 주요 출력
- broker request/result
- execution observability records
- order result / order status 관련 산출물

## 8.4 현재 핵심 책임
- guard 평가
- mode safety enforcement
- idempotent execution

## 8.5 비책임
- 승인 없이 실행하지 않는다
- 전략 판단을 하지 않는다
- 모니터처럼 entry/exit를 다시 계산하지 않는다

---

## 9. Reporter

## 9.1 목적
- runtime이 남긴 근거를 다시 읽어 operator/strategist가 소비할 수 있는 리포트와 피드백으로 바꾼다.

## 9.2 주요 입력
- canonical run artifacts
- direct run/trade artifacts
- event logs
- lifecycle bundle
- linked evidence / provenance

## 9.3 주요 출력
- operator brief
- AI trade report
- daily report
- reporter analysis
- recent strategy feedback / strategy memory advisory surface

## 9.4 현재 핵심 책임
- read-only post-run analysis
- deterministic baseline + optional AI review
- 전략 피드백용 compact memory 생성

## 9.5 비책임
- runtime decision을 바꾸지 않는다
- live execution control state를 수정하지 않는다
- UI adapter에 과도하게 의존하지 않는 방향으로 가야 한다

## 9.6 현재 상태 평가
Reporter는 중요하지만, 현재 단계에서는 “하나의 agent node”보다 **reporting subsystem**으로 보는 것이 더 정확하다.

---

## 10. handoff를 실제 운영 기준으로 다시 쓰면

## 10.1 Commander → Strategist
- route context
- selected/applied policy provenance context
- strategist가 읽어야 할 상위 의도

Commander는 여기서 “어떤 전략 frame이 필요한지” 방향을 정리하고, Strategist는 그 방향을 policy proposal로 구체화한다.

## 10.2 Strategist → Scanner
- playbook
- themes / avoid_themes
- scanner bias / priority
- scanner-related policy hints

Scanner는 이를 바탕으로 실제 감시 대상 후보군을 구성하고 순위를 매긴다.

## 10.3 Scanner → Monitor
- selected symbol
- selected feature snapshot
- ranked candidate context 중 필요한 정보

Monitor는 universe selection을 다시 하지 않고 selected symbol만 본다.

## 10.4 Monitor → Supervisor
- OrderIntent
- rationale / risk input / signal source

Supervisor는 intent를 실행 가능 상태로 만들지 막을지 결정한다.

## 10.5 Supervisor → Executor
- SupervisorDecision
- approved/modified intent

Executor는 guard와 broker call path만 책임진다.

## 10.6 Runtime / Artifacts → Reporter
- canonical artifacts
- direct trade artifacts
- event logs
- lifecycle/provenance

Reporter는 이들을 읽어 사후 분석을 만든다.

---

## 11. 가장 중요한 role boundary 한 줄 요약

- Commander: **무슨 route와 어떤 applied policy로 갈지 정하는 상위 조율자**
- Strategist: **전략/정책 proposal producer**
- Scanner: **감시 대상 선발기**
- Monitor: **selected symbol의 intent emitter**
- Supervisor: **승인/거절 관문**
- Executor: **유일한 실제 실행 경로**
- Reporter: **사후 해석 subsystem**
