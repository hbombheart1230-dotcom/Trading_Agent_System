# Agent Layer (M15)

이 문서는 Trading_Agent_System의 **M15 Agent Layer 구조**를 설명한다.

## 목표

- 전략/탐색/모니터링/리포팅/실행 조정을 **분리된 책임**으로 구성
- 실거래 API 호출은 **Execution Layer**로만 제한
- 승인(approval) 및 안전장치는 Supervisor/Execution Layer에서 일관되게 적용

## 구성

```
libs/agent/
├── commander.py   # 오케스트레이션
├── strategist.py  # 전략/계획 수립
├── scanner.py     # 후보/신호 탐색 → intent 생성
├── monitor.py     # 상태 추적(포지션/오픈 인텐트 등)
├── reporter.py    # 요약/리포트 생성
└── executor.py    # Agent 레벨 Executor (Execution Layer 호출 전 단계)
```

## 역할

### Commander
- 한 사이클(run)을 오케스트레이션
- Strategist → Scanner → AgentExecutor → Monitor → Reporter 흐름을 관리

### Strategist
- 시장/제약 조건을 받아 **Plan** 생성
- 향후 LLM/뉴스/정책을 붙이더라도 Strategist에 캡슐화

### Scanner
- Plan을 받아 **구체적인 order intent** 목록을 생성
- (초기에는 pass-through/룰 기반, 이후 점진 확장)

### AgentExecutor
- **승인 모드(approval_mode)** 와 **EXECUTION_ENABLED**를 반영
- 기존 `ExecutorAgent`(two-phase + skill runner)를 감싸는 래퍼

### Monitor
- 실행 결과를 상태 저장소(repo/state_store 등)에 반영하는 위치

### Reporter
- 실행 결과/의사결정을 사용자/UI/로그에 전달 가능한 구조로 요약

## 호출 흐름(개념)

```
Strategist → Scanner → AgentExecutor
        ↓
     Commander
        ↓
Monitor → Reporter
```
