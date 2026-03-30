# 📘 Trading Agent System Roadmap  
## Phase 5-2 ~ Phase 6 (Execution & Architecture Alignment)

---

## 🎯 목적

현재 시스템은 **매매 lifecycle이 정상 동작하는 단계**에 도달했으며,  
이 문서는 이후 **구조 안정화 → 정책 구조화 → 운영 시스템화**까지의 로드맵을 정의한다.

---

## 🧭 현재 상태 (Baseline)

- ✅ 매매 lifecycle 정상 (BUY → SELL → state 정리)
- ✅ Scanner ↔ Monitor 정합성 개선 진행 중
- ✅ Trade / Report / Brief 생성 안정화 완료
- ⚠️ Reporting 구조와 UI data_access 일부 결합 상태
- ⚠️ Strategist → Monitor 정책 전달 구조 미완성
- ⚠️ Commander는 orchestration만 수행 중 (정책 확정 없음)

---

# 🚧 Phase 5-2: UI / Reporting Read Layer 분리

## 🎯 목표
**UI 조회 로직과 Reporting 데이터 로직 완전 분리**

## 📌 문제
- apps/operator_ui/data_access* 가 UI + Reporting에서 혼용 사용
- Reporter / Batch가 UI adapter를 직접 참조
- 책임 경계 불명확

## ✅ 작업

### 1. UI 계층 고정
apps/operator_ui/data_access* → UI 전용 adapter

### 2. Reporting Read Layer 신설
libs/reporting/reporting_read_model.py

역할:
- canonical artifacts 읽기
- direct artifacts fallback
- event-log fallback
- run snapshot 구성

### 3. 의존성 분리
- Reporter / Batch → data_access 제거
- reporting_read_model 사용

---

## 🧠 구조 결과

[Runtime]  
   ↓  
[Artifacts]  
   ↓  
[Reporting Read Model]  
   ↓  
[Reporter / Brief]

[UI Data Access]  
   ↓  
[Operator UI]

---

# 🧠 Phase 5-3: Strategist → Monitor Policy 구조화

## 🎯 목표
전략을 텍스트가 아닌 “정책 객체”로 전달

## 📌 현재 문제
- Strategist → Scanner 중심 구조
- Monitor는 자체 threshold 기반 판단
- 전략과 실행 기준이 분리됨

## ✅ 작업

### Policy Schema
{
  "volume_ratio_min": 0.72,
  "pullback_min_pct": 0.008,
  "pullback_max_pct": 0.06,
  "max_extended_from_vwap_pct": 0.10,
  "reclaim_required": true,
  "preferred_entry_mode": "breakout",
  "market_regime": "defensive",
  "policy_rationale": "...",
  "scanner_bias_summary": "..."
}

---

# 🧭 Phase 5-4: Commander 정책 확정

## 🎯 목표
Strategist는 제안, Commander는 최종 결정

## ✅ 작업
- strategist_policy 수신
- applied_policy 생성
- route 및 provenance 기록

---

# 🚀 Phase 6: Production-grade Agent System

## 1. Orchestration
- 상태 기반 흐름 제어
- retry / cancel / transition

## 2. Reporting
- intraday / trade / daily report 통합

## 3. Settings
- env → policy 중심 구조

## 4. Observability
- metrics / alert / audit log

---

# 🧭 실행 순서

현재 → 정합성 유지  
→ Phase 5-2  
→ Phase 5-3  
→ Phase 5-4  
→ Phase 6

---

# ⚠️ 핵심 원칙

- Monitor는 기준 축 (수정 최소화)
- Scanner는 정합성 보정
- Strategist는 정책 생성
- Commander는 최종 결정
- Reporter는 사후 분석

---

# 🔥 한 줄 요약

지금은 “정합성 단계” →  
다음은 “정책 구조화” →  
최종은 “운영 가능한 에이전트 시스템”
