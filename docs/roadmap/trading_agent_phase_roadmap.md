# Trading Agent System – Phase Roadmap (5-2 ~ Phase 6)

## Current Focus (Pre 5-2)
- Scanner ↔ Monitor 정합성 조정
- Compatibility bias 튜닝
- Lifecycle / Report / Brief 안정화 완료 상태 유지

---

## Phase 5-2: UI data_access 분리

### 목표
- UI 전용 adapter와 Reporting read-model 분리

### 작업
- apps/operator_ui/data_access* → UI 전용 유지
- libs/reporting/reporting_read_model.py 신설
- Reporter / Batch에서 data_access 의존 제거

---

## Phase 5-3: Strategist → Monitor Policy Schema

### 목표
- 전략가 정책을 구조화하여 Monitor가 직접 사용

### 포함 필드
- volume_ratio_min
- pullback_min/max_pct
- max_extended_from_vwap_pct
- reclaim_required
- preferred_entry_mode
- policy_rationale

---

## Phase 5-4: Commander Policy 확정

### 목표
- Strategist는 제안, Commander는 확정

### 작업
- applied_policy 생성
- policy provenance 기록
- route 판단 (cached/full/monitor_only)

---

## Phase 6: Production-grade Agent System

### 1. Orchestration
- LangGraph 기반 state machine 강화
- retry / cancel / transition 관리

### 2. Reporting/Operator
- intraday / trade / daily report 통합
- operator console 완성

### 3. Settings 통합
- env → policy 중심 구조 전환

### 4. Observability
- metrics / alert / audit log
- incident 대응 체계 구축

---

## Execution Order

1. (현재) 정합성 유지 및 검증
2. Phase 5-2
3. Phase 5-3
4. Phase 5-4
5. Phase 6

---

## 핵심 원칙

- Monitor는 기준 축 (수정 최소화)
- Scanner는 정합성 보정
- Strategist는 정책 생성
- Commander는 최종 결정
- Reporter는 사후 분석
