# 📘 Trading Agent System Roadmap Addendum  
## Phase 5-2, 5-2-2, 5-3 Clarification

---

## 🎯 목적

본 문서는 기존 `phase_5_to_6.md`를 변경하지 않고,  
Phase 5-2와 Phase 5-3 사이에서 발생하는 **뉴스 → 종목 연결 가시화 단계(5-2-2)**를 명확히 정의한다.

---

## 🧭 전체 흐름

Phase 5-2 → Phase 5-2-2 → Phase 5-3

| 단계 | 역할 |
|------|------|
| 5-2 | 구조 분리 (UI vs Reporting) |
| 5-2-2 | 뉴스 → 종목 연결 가시화 |
| 5-3 | 정책 구조화 (Strategist → Monitor) |

---

# 🚧 Phase 5-2 (구조 분리)

## 목표
- UI data_access와 Reporting read-model 완전 분리

## 핵심 작업
- apps/operator_ui/data_access* → UI 전용
- reporting_read_model 신설
- Reporter/Brief에서 UI data_access 제거

---

# 🔍 Phase 5-2-2 (가시화 단계)

## 목표
- 뉴스 → 전략가 → 스캐너 → 종목 선택 흐름을 사람이 이해할 수 있게 보여줌

## 현재 문제
- 뉴스와 종목 선택 간 연결이 리포트에서 보이지 않음
- 이미 데이터는 존재하지만 연결이 약함

## 해결 방식
- 기존 artifact 기반으로 read-model에서 조립

## 구현 내용

1. 뉴스 → 전략가 해석  
- market headlines  
- global sentiment  
- playbook  

2. 전략가 → 스캐너 연결  
- symbol constraints  
- candidate_limit  
- scanner_priority  

3. 스캐너 → 종목 선택  
- candidate ranking table  
- score drivers  
- selection reason  

4. 최종 리포트 출력  

뉴스 → 전략가 판단 → 후보 비교 → 종목 선택

---

## 특징

- 기존 로그 재작성 ❌  
- 기존 artifact 활용 ⭕  
- read-model / report assembly 개선 중심  

---

# 🧠 Phase 5-3 (정책 구조화)

## 목표
- 전략가가 정책 객체를 내려주고 Monitor가 직접 사용

## 핵심 작업
- strategist output schema 확장  
- policy object 생성  
- monitor/scanner가 policy 직접 참조  

---

## 예시

{
  "volume_ratio_min": 0.72,
  "preferred_entry_mode": "breakout",
  "reclaim_required": true,
  "policy_rationale": "defensive market"
}

---

# ⚠️ 차이 요약

| 구분 | 5-2-2 | 5-3 |
|------|------|------|
| 목적 | 설명력 개선 | 실행 구조 개선 |
| 대상 | 리포트 / 브리프 | 전략가 / 모니터 |
| 방식 | 조립 | 정책화 |
| 영향도 | 낮음 | 높음 |

---

# 🚀 실행 순서

1. Phase 5-2 (구조 분리)  
2. Phase 5-2-2 (가시화)  
3. Phase 5-3 (정책 구조화)  

---

# 🔥 한 줄 정리

- 5-2-2는 “보이게 만드는 단계”  
- 5-3은 “실제로 그렇게 동작하게 만드는 단계”  
