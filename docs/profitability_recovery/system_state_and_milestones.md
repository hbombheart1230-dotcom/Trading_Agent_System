# SALT (Trading Agent System) Master State & Milestones

**마지막 업데이트:** 2026년 4월 기준 (Profitability Recovery Phase 진입)
**문서 목적:** 현재 SALT 프로젝트의 전체 아키텍처 상태, 진행 중인 마일스톤, 에이전트별 현재 상황 및 절대 준수 원칙(Non-negotiable Rules)을 한곳에서 파악하기 위한 마스터 문서입니다.

---

## 1. 시스템 정체성 및 핵심 아키텍처 (As-Is)

SALT는 LangGraph 기반의 7-에이전트 멀티 트레이딩 시스템입니다.
**"Commander가 런타임 흐름을 결정하고, Strategist가 정책을 제안하며, Scanner가 후보를 고르고, Monitor가 진입/청산 의도를 생성하며, Supervisor/Executor가 승인과 실행을 담당하고, Reporter가 사후 분석을 수행한다."**

### 1.1 핵심 불변 원칙 (Non-negotiable Rules)
1. **No Human Approval & Supervisor Mandatory:** 사람은 매번 승인하지 않으며, 모든 주문은 반드시 `Supervisor`의 자동 승인과 가드를 거쳐야만 실행(Executor)됩니다.
2. **Role Boundaries:** `Monitor`는 오직 주문 의도(OrderIntent)까지만 생성합니다. 직접 실행하지 않습니다.
3. **Single Source of Truth:** 리포트와 UI는 파편화된 로그가 아닌, 각 노드가 기록한 `Canonical Artifact`(예: monitor.json)를 최우선으로 신뢰합니다.
4. **Additive Migration:** 하위 호환성을 깨는 대공사 대신, 기능을 덧붙이고 Feature Flag를 통한 점진적 이관을 원칙으로 합니다.

---

## 2. 현재 진행 중인 핵심 마일스톤 (Current Milestones)

현재 시스템은 **Phase 5-4 (Ownership 정립) 및 Phase 6-1 (Reporting 고도화)** 단계에 있으며, 최근(2026-04-14) **Profitability Recovery (수익성 회복)** 페이즈에 돌입했습니다.

### 2.1 Profitability Recovery (2026-04-14 ~ )
*   **목표:** 매매 손실 구조적 진단 및 Lifecycle(진입→유지→청산→실행→리포트) 완결성 확보
*   **제약 사항 (Strict):** **전략 로직이나 임계치 수정 절대 금지.** 오직 가시성(Observability) 및 로깅 강화, 체결 필드 캡처 등 관측성 개선만 허용됩니다.

### 2.2 Kiwoom Agentic Trader Plan (v2)
*   **완료 (M1~M8):** HTTP/Token 클라이언트 구축, Mock/Real Executor 분리, `TradeDecisionPacket` 계약 확립.
*   **진행/예정 (M9~M10):** 
    *   **M9 (Read Layer 표준화):** 전략/감독관용 포트폴리오 및 시장 스냅샷 제공.
    *   **M10 (State/Portfolio 저장소):** 잔고/당일 손익 등 Supervisor 자동 입력을 위한 계산 및 상태 저장(`state.json`).

### 2.3 Phase 5-4 & 6-1 (실전 고도화 및 소유권 정리)
*   **Phase 5-4:** Commander의 의사결정 권한(Routing, Policy) 강화, Strategist를 '제안자(Proposal Owner)'로 역할 축소, Scanner-Monitor 간 호환성 가시성 확보.
*   **Phase 6-1:** 결정론적(Deterministic) 리포팅을 위한 `Read-model` (Trade, Daily, Symbol) 도입. 사실(Fact)은 코드로, 요약/해석(Narrative)만 LLM으로 분리.

---

## 3. 에이전트별 현재 상태와 개선 방향

### 3.1 지휘자 (Commander)
*   **As-Is:** 단순 파이프라인 오케스트레이터 역할.
*   **To-Be (Phase 5-4):** 명확한 결정론적(Deterministic) 최고 책임자. Strategist 호출 여부, 라우팅, 적용 정책(Applied Policy), No-trade posture의 최종 소유권 확보 (LLM 사용 배제).

### 3.2 전략가 (Strategist)
*   **As-Is:** 사실상 상위 뇌(Brain)처럼 동작하며 최종 의사결정에 과도하게 개입.
*   **To-Be (Phase 5-4):** 시장 맥락 해석, Playbook, Entry/Exit Policy를 제안(Proposal)만 하는 **정책 제안자**.

### 3.3 스캐너 (Scanner)
*   **As-Is:** 후보군 수집 및 평가 수행. 대형 유동성 종목(삼성전자 등) 쏠림 현상 관찰됨 (trading_value 가중치 > volume_surge).
*   **To-Be & Issues:** 종목 쏠림 현상 튜닝은 현재 진행 중인 Monitor Scoring 검증에 혼선을 주지 않기 위해 의도적으로 **보류(On Hold)**. 향후 Defensive Playbook 등에서만 가중치를 완화하는 방안(안 B) 검토 예정.

### 3.4 모니터 (Monitor)
*   **As-Is:** 조건들이 겹겹이 쌓인 Hard-filter 구조로 인해 과도한 매매 포기(No-trade) 발생. (Phase 5-1-2 진행 중)
*   **진행 중인 개선 (Scoring System):** 
    *   필수 안전장치만 Hard Filter로 남기고, VWAP Reclaim, Volume, Breakout 등은 점수제(Scoring)로 전환.
    *   현재 Shadow Mode로 기록 및 검증 중이며, 결과 안정 시 Primary로 전환 예정.
    *   `pullback_timing` 등 뭉뚱그려진 Blocker를 `pullback_not_mature` 등 Raw Blocker 단위로 쪼개어 가시성 대폭 강화.

### 3.5 리포터 (Reporter)
*   **As-Is:** 각 리포트가 개별적으로 로그를 해석하여 사실(Fact)과 내러티브가 혼재됨.
*   **To-Be (Phase 6-1):** `Trade`, `Daily`, `Symbol` 단위의 결정론적 읽기 모델(Read-model) 구축. LLM은 이 Read-model 데이터를 바탕으로 논평과 요약만 수행하도록 분리.

---

## 4. 운영 및 개발 규칙 (Codex & Dev Guidelines)

1. **수익성 회복 페이즈 최우선:** 매매 로직, 가드, 임계치(Threshold) 수정 절대 금지. 오직 관측성(Observability) 및 데이터 연동 버그 수정만 허용.
2. **결정론 우선:** Commander 결정 및 Report의 팩트(Metrics, Blockers 등) 수집 과정에 LLM 도입 금지.
3. **점진적 패치 (Additive Changes):** 기존의 DTO 필수 필드나 `reports/trades/` 디렉터리 구조를 깨지 않고, 새 필드나 기능을 덧붙이는 방식(Metadata, Shadow Mode)으로 이관.
4. **명확한 소유권 명시:** 데이터의 원천(Source of truth)을 명확히 할 것. (예: `commander_applied_policy`, `strategist_proposal`)