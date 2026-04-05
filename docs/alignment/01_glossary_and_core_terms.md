# 01. Glossary and Core Terms

## 1. 목적

이 문서는 Trading Agent System에서 반복적으로 등장하는 용어를 한 번에 고정하기 위한 용어집이다.  
특히 `policy`, `intent`, `applied_policy`, `canonical artifact`, `reporting read model` 같은 단어는 문맥에 따라 쉽게 흔들릴 수 있으므로, 여기서 기준 정의를 먼저 맞춘다.

---

## 2. 런타임 / 상태 / 추적 용어

### run_id
하나의 런 사이클을 추적하는 공통 키.  
전략가, 스캐너, 모니터, 감독관, 수행자, 리포터가 같은 사이클을 공유했다는 것을 묶는 기준 식별자다.

### runtime phase
장전 / 장중 / 장후처럼 런타임이 어떤 구간에 있는지를 나타내는 상태.  
Commander가 route를 정하거나 특정 fast-path를 택할 때 핵심 조건으로 쓰인다.

### path / route
현재 런이 어떤 실행 경로를 탔는지에 대한 의미.  
예를 들어 full-cycle, cached strategist 재사용, holding 상태에서 monitor 중심 흐름 같은 것이 여기에 해당한다.

### state
그래프/런타임이 공유하는 현재 작업 메모리.  
각 노드는 state를 읽고 additive하게 결과를 붙이며 다음 노드가 그 결과를 소비한다.

---

## 3. 정책 / 해석 / 의사결정 용어

### policy
전략 또는 의사결정 기준을 객체 형태로 정리한 것.  
텍스트 설명이 아니라 downstream agent가 읽을 수 있는 구조화된 판단 기준을 뜻한다.

### interpretation policy
모니터가 low-level signal과 higher-level structure를 어떤 의미로 해석할지에 대한 정책.  
5-4에서 Strategist proposal → Commander applied → Monitor consumer 구조로 정리하려는 대상이다.

### threshold policy
기존 threshold/gate 중심 판단 기준.  
장기적으로는 primary owner에서 fallback safety로 내려갈 방향이지만, 현재는 여전히 중요한 최종 안전 경계다.

### applied policy
Commander가 여러 후보 정책 소스 중 실제 런타임에서 공식적으로 적용한다고 확정한 정책.  
source-of-truth 관점에서 매우 중요하다.

### provenance
어떤 결정이나 정책이 어디서 왔는지에 대한 출처 정보.  
policy source chain, selected source, applied source 같은 메타데이터가 여기에 해당한다.

### legacy gate
기존 threshold 기반의 BUY/WAIT 최종 안전 경계.  
현재 단계에서는 여전히 final decision safety owner이며, policy-driven wiring이 성숙하기 전까지는 제거 대상이 아니다.

### policy-aware decision
정책 객체를 실제 판단 로직에 반영하는 방향을 뜻한다.  
단순 설명용 interpretation에 머물지 않고 최종 BUY/WAIT 판단 비중을 점진적으로 가져오는 구조를 의미한다.

---

## 4. 주문 / 실행 / 안전 용어

### OrderIntent
Monitor가 만드는 “실행 전 intent-to-order” 패킷.  
실제 주문이 아니라, 감독관과 실행 계층으로 넘겨질 표준화된 의도 패킷이다.

### SupervisorDecision
Supervisor가 OrderIntent에 대해 내리는 승인 / 거절 / 수정 결정.  
실행 계층으로 넘어갈 수 있는 유일한 승인 관문이다.

### approval
의도를 실행 후보로 인정하는 단계.  
하지만 approval이 곧 execution을 보장하지는 않는다.

### guard
최종 실행 안전 경계.  
실행 활성화 여부, 실제 계좌 허용 여부, 종목 allowlist, 수량/금액 제한, idempotency 등이 여기에 포함된다.

### idempotency
같은 intent_id가 중복 실행되지 않도록 보장하는 성질.  
실행 계층에서 매우 중요한 안정성 규칙이다.

---

## 5. 에이전트 / 역할 용어

### Commander
오케스트레이션, route selection, applied policy/provenance 정리의 owner.  
장기적으로는 상위 operating posture owner로 강화될 대상이다.

### Strategist
시장/전략 해석과 정책 proposal 생성의 owner.  
5-4 이후에는 상위 지휘자가 아니라 “정책 제안 + 전략 구현” 역할로 더 명확히 정리될 필요가 있다.

### Scanner
후보 종목을 정량화하고 top candidate를 고르는 선발 계층.

### Monitor
선택된 종목에 대해 entry/exit를 감시하고 OrderIntent를 만드는 consumer.  
실행은 하지 않는다.

### Supervisor
OrderIntent를 승인/거절/수정하는 정책/위험 통제 계층.

### Executor
승인된 의도를 실제 브로커 호출 경로로 연결하는 유일한 실행 계층.

### Reporter
로그/아티팩트 기반 사후 해석 및 리포트 생성 계층.  
현재는 단일 agent라기보다 reporting subsystem의 성격이 더 강하다.

---

## 6. 아티팩트 / 리포팅 용어

### canonical run artifact
각 노드가 실행 시점에 `reports/canonical/<date>/<run_id>/...` 아래에 직접 기록하는 1차 truth 아티팩트.  
downstream reporting과 operator UI의 가장 우선적인 정보원이다.

### direct artifact
트레이드 레벨 또는 리포트 레벨에서 바로 생성되는 산출물.  
canonical artifact가 없거나 부족할 때 함께 사용된다.

### event log
런타임 이벤트 JSONL.  
추적/진단/보조 근거 역할을 하며, canonical artifact가 있으면 일반적으로 우선순위는 더 낮다.

### reporting read model
리포팅/브리프/배치가 사용할 수 있도록 canonical artifact, direct artifact, event log를 읽어 하나의 snapshot으로 조립하는 읽기 계층.  
5-2의 핵심 주제였다.

### operator brief
운영자에게 빠르게 보여주는 run 또는 trade 수준의 짧은 해석 결과.

### AI trade report
개별 trade lifecycle에 대한 사후 회고 보고서.

### daily report
당일 전체 흐름을 요약하는 보고서.

### strategy memory / recent strategy feedback
Reporter가 요약한 최근 전략 성과/약점/권고를 Strategist가 advisory context로 재사용하는 surface.

---

## 7. 현재 ownership 정리에 특히 중요한 용어

### source of truth
어떤 항목의 최종 owner가 누구인지 정의하는 기준.  
예:
- selected symbol의 source-of-truth는 Scanner
- entry/exit intent의 source-of-truth는 Monitor
- execution allow/block의 source-of-truth는 Supervisor/Guard
- applied policy의 source-of-truth는 Commander

### ownership migration
현재 owner와 목표 owner가 다른 영역을 점진적으로 옮기는 과정.  
5-4의 핵심은 decision-expansion보다 ownership/wiring 정리다.

### wiring
상위 producer가 만든 정보를 하위 consumer가 어떤 contract surface를 통해 읽는지에 대한 연결 정의.  
정책 migration에서 ownership만큼 중요하다.
