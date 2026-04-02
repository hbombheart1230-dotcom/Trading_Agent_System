# Phase 5-3-2 — Chart Structure Feature Candidates

## 1. 목적

Monitor의 진입/청산 판단을 단순 threshold 기반에서 벗어나  
**차트 구조 기반 해석으로 확장하기 위한 feature 후보 정의 단계**

본 단계는 구현이 아니라 **설계 고정**이 목적이다.

---

## 2. 배경

현재 Monitor는 다음 신호에 강하게 의존:

- reclaim
- breakout
- pullback
- volume
- extension
- confidence

문제:

- 구조적 맥락 부족
- 연속성/추세 해석 부족
- 청산 로직이 단순함

---

## 3. Feature 그룹 정의

### 3.1 MA Cross / Alignment

- ma_alignment_state
- ma_slope_state
- ma_reclaim_state

의미:
- 추세 정렬 / 추세 유지 / 추세 약화

---

### 3.2 Support / Resistance

- resistance_break_state
- support_retest_state
- support_hold_state
- support_break_state

의미:
- 돌파의 질
- 지지 전환
- 구조 붕괴

---

### 3.3 Structure

- structure_hh_hl_state
- structure_break_state
- trend_channel_position

의미:
- higher high / higher low 유지
- 추세 구조 유지 여부

---

### 3.4 Continuity

- follow_through_state
- volume_continuity
- momentum_decay_state

의미:
- 흐름 유지 여부
- 상승 지속성
- 탄력 약화

---

## 4. 진입 관점 활용

- breakout이 구조적으로 유효한지 판단
- pullback이 건강한 눌림인지 판단
- reclaim이 약해도 구조가 유지되는지 판단

---

## 5. 청산 관점 활용

- 구조 붕괴 (HH/HL 깨짐)
- 지지 이탈
- 연속성 붕괴
- 추세 약화

---

## 6. Feature 분류

각 feature는 아래로 분류:

- hard (절대 조건)
- soft (가중치 요소)
- explanatory (설명용)

---

## 7. 기존 signal_evidence와 관계

- signal_evidence = 미시 신호
- chart_structure_features = 거시 구조

둘은 결합되어야 함

---

## 8. Non-Goals

- decision 로직 변경 없음
- threshold 제거 없음
- LLM 해석 없음
- runtime wiring 없음

---

## 9. 한 줄 요약

차트 구조 기반 feature vocabulary를 정의하여  
Monitor를 구조 해석 기반으로 확장하기 위한 설계 단계
