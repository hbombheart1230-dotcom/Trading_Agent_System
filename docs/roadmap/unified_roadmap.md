# 📘 Trading Agent System Unified Roadmap (Clean Version)

---

## 🎯 목적

본 문서는 기존 roadmap 및 addendum 문서들을 통합하여  
실행 순서와 역할이 명확한 단일 로드맵으로 정리한 것이다.

---

## 🧭 전체 흐름

### Phase 5 (정합성 → 구조화)

#### 5-1: 장중 검증
- 실제 매매 lifecycle 검증
- 로그 기반 문제 식별

---

#### 5-1-2: Monitor Scoring 도입 (Shadow)
- scoring 로직 additive 도입
- shadow mode 검증
- 기존 로직 유지

---

#### 5-2: 구조 분리
- UI data_access 분리
- reporting_read_model 도입

---

#### 5-2-1: Pre-buy strategist refresh
- 전략가 호출 타이밍 개선
- stale 전략 방지

---

#### 5-2-2: 가시화 (뉴스 → 종목 연결)
- 뉴스 → 전략가 → 스캐너 → 선택 흐름 연결
- read-model 기반 조립

---

#### 5-2-3: Report Refinement
- trade → daily → strategist input 구조 구축
- 리포트를 전략 입력 데이터로 전환

---

#### 5-3: 정책 구조화
- Strategist → policy object 생성
- Monitor가 policy 직접 사용

---

#### 5-3-2: 차트 구조 feature 후보 정의
- MA cross / 지지저항 / 구조 / 연속성 후보 정의
- 아직 구현하지 않음 (설계만)

---

#### 5-4: Commander 정책 확정
- strategist proposal → commander applied_policy
- policy ownership 명확화

---

## 🚀 Phase 6 (Production System)

### 6-1 Orchestration
- LangGraph 기반 state machine

### 6-2 Reporting
- intraday / trade / daily 통합

### 6-3 Settings
- env → policy 전환

### 6-4 Observability
- metrics / alert / audit

---

## ⚠️ 핵심 원칙

- Monitor는 최소 수정 유지
- 정책은 strategist/commander로 이동
- 리포트는 전략 입력 데이터로 사용
- 모든 변경은 additive

---

## 🔥 한 줄 요약

지금은 “정합성 → 구조 분리 → 가시화 → 리포트 → 정책 → 운영” 순서로 진행한다.
