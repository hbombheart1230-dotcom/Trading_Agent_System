# Phase 6 Kickoff — Read Model & Consumption Layer

## 목적
Phase 5-4에서 완성된 decision system을 기반으로,
deterministic read-model과 reporting consumption 구조를 도입한다.

---

## 1. Phase 6 정의

“결정된 결과를 읽고, 활용하고, 축적하는 시스템 구축”

---

## 2. 핵심 변화

### Before (Phase 5-4)
- decision 중심
- agent orchestration
- policy control

### After (Phase 6)
decision → read-model → report → feedback → strategist

---

## 3. 핵심 원칙

### 3.1 Read-model은 deterministic only
- LLM 사용 금지
- canonical artifact 우선
- direct artifact 보조
- event log fallback

### 3.2 Fact vs Narrative 분리
- facts: deterministic
- summary / lesson / recommendation: LLM

### 3.3 Source-of-truth 유지
- Commander = primary truth
- Strategist = proposal
- Monitor = signal

---

## 4. Phase 6 구성

### 6-1: Read Model Layer
- trade_read_model
- daily_summary_read_model
- symbol_read_model

### 6-2: Reporting Refactor
- AI Trade Report
- Operator Brief
- Daily Report

### 6-3: Strategist Consumption
- strategist_feedback input 강화
- deterministic pack 기반 입력

---

## 5. 실행 순서

1. trade_read_model
2. daily_summary_read_model
3. symbol_read_model
4. reporting refactor

---

## 6. 완료 기준

- trade 단위 데이터 deterministic 접근 가능
- daily 단위 집계 가능
- symbol 단위 패턴 분석 가능
- strategist input pack 생성 가능

---

## Final Statement

Phase 6는 시스템을 “사용 가능한 상태”로 만드는 단계다.
