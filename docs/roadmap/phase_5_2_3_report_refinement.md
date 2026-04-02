# 📘 Phase 5-2-3: Report Refinement  
## (Trade → Strategy Feedback Loop 구축)

---

## 🎯 목적

Phase 5-2-3은 기존 리포트 구조를 단순 출력물이 아닌  
**전략가(Strategist)가 실제로 활용할 수 있는 데이터 자산으로 전환**하는 단계이다.

현재 시스템은:

- Trade / Daily / Brief 리포트가 존재하지만
- 구조적으로 분리되어 있고
- “스토리 연결”과 “학습 데이터화”가 부족하다

본 단계의 목표는:

> 리포트를 “사람이 읽는 문서”에서  
> “전략가가 학습/판단에 사용하는 데이터”로 전환하는 것이다.

---

## 📍 위치 (로드맵 기준)

Phase 5-2 → Phase 5-2-2 → **Phase 5-2-3 (현재 단계)** → Phase 5-3

---

## ⚠️ 전제 조건

- Phase 5-2 완료
- Phase 5-2-2 완료

---

## 🚧 현재 문제

- 리포트가 스토리 구조 없음
- 전략가 입력으로 활용 불가
- 데이터는 있으나 연결 없음

---

## 🧠 목표 구조

### 1️⃣ Trade Report

- Entry / Holding / Exit / Evaluation 구조
- trade story 완성

### 2️⃣ Daily Report

- 집계 기반 패턴 분석
- 성공/실패 구조 추출

### 3️⃣ Strategist Input Summary

- 전략가가 바로 사용할 수 있는 요약 데이터

---

## 🔄 흐름

Trade Data  
→ Trade Report  
→ Daily Report  
→ Strategist Input  
→ Strategist

---

## 🚀 구현 범위

- read-model 기반 조립
- 데이터 구조 정의

---

## ❌ 제외

- 전략 로직 변경
- monitor 변경
- execution 변경

---

## 🔥 핵심 한 줄

리포트는 출력물이 아니라 전략 입력 데이터다.
