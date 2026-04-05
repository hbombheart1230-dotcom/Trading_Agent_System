# 02. Current System Definition (As-Is)

## 1. 이 문서의 목적

이 문서는 “현재 시스템이 실제로 무엇인가”를 정의한다.  
즉, 이상적인 목표 구조가 아니라 **지금 repository와 roadmap 문서가 가리키는 현재 상태**를 정리한다.

이 문서를 읽고 나면 최소한 다음 질문에는 답할 수 있어야 한다.

- 지금 Commander는 실제로 무엇을 하는가
- Strategist는 어디까지 owner인가
- Scanner와 Monitor는 어떤 경계를 갖는가
- Reporter는 agent인가 subsystem인가
- 5-3-2가 끝난 지금 무엇이 준비되었고 무엇이 아직 migration 중인가

---

## 2. 현재 시스템을 한 문장으로 정의하면

현재 Trading Agent System은 다음과 같이 정의할 수 있다.

> **Commander가 런타임 흐름과 policy provenance를 정리하고, Strategist가 전략/정책 proposal을 만들고, Scanner가 top candidate를 고르고, Monitor가 entry/exit intent를 만들고, Supervisor와 Executor가 승인/실행을 담당하며, Reporter가 사후 분석을 수행하는 LangGraph 지향 멀티에이전트 트레이딩 시스템**

이 정의에서 중요한 포인트는 세 가지다.

1. 현재 구조는 이미 명확한 역할 분리를 상당 부분 갖추고 있다.
2. 그러나 policy ownership과 decision ownership은 아직 migration 중이다.
3. Reporter는 운영상 중요하지만 아직 단일 agent보다 subsystem 성격이 더 강하다.

---

## 3. 현재 구조의 큰 층위

현재 구조는 개념적으로 아래 다섯 층으로 읽는 것이 가장 정확하다.

### 3.1 Agent / Decision Layer
- Commander
- Strategist
- Scanner
- Monitor

### 3.2 Approval Layer
- Supervisor

### 3.3 Execution Layer
- Executor / broker call path / guards

### 3.4 Contract Layer
- strategy/scanner/monitor/supervisor DTO
- policy contract
- canonical artifact schema

### 3.5 Observability / Reporting Layer
- canonical artifacts
- direct artifacts
- event logs
- operator brief
- trade report
- daily report

이렇게 보면 “에이전트 시스템”이면서도 실제 운영 가능한 시스템으로 가기 위해 observability와 reporting이 독립 층으로 꽤 크게 성장해 있다는 점이 보인다.

---

## 4. 현재 구조의 핵심 불변 규칙

현재 시스템을 이해할 때 가장 먼저 고정해야 하는 불변 규칙은 아래다.

### 4.1 Monitor는 intent까지만 간다
Monitor는 OrderIntent를 만들 뿐 직접 주문을 넣지 않는다.  
이 경계가 무너지면 Agent Layer와 Execution Layer 분리가 무너진다.

### 4.2 Execution은 승인과 guard 뒤에서만 일어난다
Supervisor 승인과 Execution Layer guard를 모두 통과해야만 실제 주문으로 이어진다.

### 4.3 canonical artifact가 downstream truth의 최우선이다
가능하면 downstream reporting과 operator UI는 event log가 아니라 canonical artifact를 우선적으로 읽는다.

### 4.4 additive migration이 기본 원칙이다
기존 구조를 한 번에 뒤집지 않고, compatibility와 rollback 가능성을 유지하면서 ownership과 wiring을 점진적으로 옮긴다.

---

## 5. 현재 상태의 본질: 이미 잘 된 부분과 아직 migration 중인 부분

### 5.1 이미 잘 된 부분

#### A. lifecycle 자체는 상당히 정리됨
BUY → SELL → state 정리 → report 생성이라는 큰 lifecycle은 이미 성숙한 편이다.

#### B. Scanner/Monitor 축은 시스템답게 정리되는 중
Scanner가 후보를 고르고 Monitor가 intent만 낸다는 큰 경계는 상당히 선명하다.

#### C. policy-aware Monitor의 foundation이 생김
5-3을 통해 Monitor는 단순 threshold reaction engine에서 policy consumer로 옮겨갈 준비를 갖췄다.

#### D. canonical artifact 중심 관측 구조가 정리됨
각 노드가 per-run artifact를 직접 쓰는 흐름이 리포팅과 운영 UI를 안정시키는 기반이 된다.

### 5.2 아직 migration 중인 부분

#### A. final BUY/WAIT ownership
현재 최종 BUY/WAIT 안전 경계는 아직 legacy gate 비중이 크다.  
policy-aware layers는 해석/설명/narrow integration까지는 들어왔지만 최종 owner 전환은 아직 아니다.

#### B. Commander ownership
Commander는 이미 route/provenance/applied policy 쪽의 owner에 가깝지만, 상위 market operating posture owner로 완전히 정리되었다고 보긴 이르다.

#### C. Strategist 권한 범위
Strategist는 현재 전략가이면서 동시에 정책 producer 역할이 강하다.  
5-4에서는 proposal owner로 더 명시적으로 정리될 필요가 있다.

#### D. Reporter 정체성
Reporter는 중요하지만, “단일 agent”로 읽기보다는 reporting subsystem으로 읽는 것이 아직 더 자연스럽다.

---

## 6. 현재 런타임 흐름을 as-is로 읽는 법

지금 구조를 가장 실무적으로 이해하는 방법은 아래 순서다.

### 6.1 Commander
- runtime phase를 본다
- 현재 holding/flat 상태와 cache 상태를 본다
- route를 정한다
- 어떤 policy source를 공식값으로 볼지 provenance를 남긴다

### 6.2 Strategist
- 시장/뉴스/감성/context를 바탕으로 전략 frame과 policy proposal을 만든다
- downstream이 읽을 수 있는 scanner/monitor 관련 정책 surface를 만든다

### 6.3 Scanner
- 후보군을 구성/점수화한다
- top candidate를 고른다
- operator-facing ranked summary를 남긴다

### 6.4 Monitor
- selected symbol을 감시한다
- entry/exit 신호를 policy와 evidence 기준으로 해석한다
- OrderIntent를 만든다
- 하지만 직접 실행하지는 않는다

### 6.5 Supervisor / Executor
- intent를 승인/거절/수정한다
- 실행 guard를 통과한 것만 실제 broker call로 보낸다

### 6.6 Reporter
- canonical artifact / direct artifact / event log를 읽는다
- brief / trade report / daily report / feedback memory를 만든다

---

## 7. 현재 구조를 한 장으로 요약하면

현재 구조는 아래 문장으로 요약할 수 있다.

> **“Threshold-heavy runtime 위에 policy-aware consumption layer를 얹어 놓은 상태이며, Strategist proposal → Commander applied policy → Monitor consumer 구조를 명확히 만드는 5-4 직전 단계”**

즉,
- 5-3-2까지는 준비 단계
- 5-4는 ownership/wiring 정리 단계
- 6은 운영 시스템 완성 단계

라고 보는 게 맞다.

---

## 8. 지금 단계에서 가장 중요한 해석 포인트

### 8.1 5-3은 decision replacement가 아니었다
5-3의 목적은 final owner를 바로 바꾸는 것이 아니라 Monitor를 policy-aware decision readiness 상태로 만드는 것이었다.

### 8.2 5-4는 logic expansion보다 ownership/wiring 정리다
이 단계에서 더 복잡한 판단 로직을 먼저 늘리면 ownership이 더 꼬일 수 있다.

### 8.3 Reporter 문제는 기능 부족보다 boundary 문제다
report가 없는 것보다, 어디까지가 runtime이고 어디부터가 post-run인지 ownership이 흐릴 때 더 큰 문제가 된다.

---

## 9. 현재 시스템에 대한 운영자 관점의 실전 정의

운영자 관점에서 지금 시스템을 이해할 때는 아래 질문으로 보면 된다.

- 이번 run의 route는 누가 정했나? → Commander
- 이번 전략과 policy proposal은 누가 만들었나? → Strategist
- 이번에 감시할 종목은 누가 골랐나? → Scanner
- 왜 아직 BUY가 안 나왔나? → Monitor evidence / policy alignment / legacy gate
- 왜 실행이 안 됐나? → SupervisorDecision 또는 Execution guard
- 나중에 왜 그렇게 됐는지 어디서 보나? → canonical artifact + report

이 관점이 장중 평가와 장후 리포트 검토 모두에 가장 유용하다.
