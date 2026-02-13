# Trading Agent System – M14 이후 구조 정리

생성일: 2026-02-12T07:42:34.959109Z

---

## 1. M14 이후 핵심 변화 요약

### 1) API Catalog 자동 빌드
- `scripts/build_api_catalog.py`
- 원본 JSONL → 통합 `api_catalog.jsonl` 생성
- 스킬 → API 매핑 기반으로 자동 호출

### 2) Composite Skill Runner
- 스킬 단위 실행 (`market.quote`, `order.place`, `order.status`)
- 룰 기반 파라미터 매핑
- DTO 정규화

### 3) Supervisor (2-Phase Intent 모델)
- 전략/사용자 요청 → Intent 생성
- `APPROVAL_MODE=manual|auto`
- 승인 전에는 절대 주문 실행 안 됨

### 4) Execution Guard (안전장치)
- `KIWOOM_MODE=mock|real`
- `EXECUTION_ENABLED=true|false`
- `SYMBOL_ALLOWLIST` (없으면 가드 비활성)
- 중복 승인 방지 (idempotent approve)

### 5) ToolFacade (NL → Skill 연결)
- 자연어 라우팅
- 승인/거절/최근주문/현재가/주문조회 처리
- 환경 로딩 (Settings.from_env)

---

## 2. 현재 아키텍처 개념도

전략가/사용자
    ↓
ToolFacade (NL Router)
    ↓
Supervisor (Intent 관리)
    ↓ 승인 필요
Execution Guard
    ↓
CompositeSkillRunner
    ↓
Execution Executor (HTTP)
    ↓
Kiwoom API

---

## 3. 실행 모드별 운영 방식

### Mock 개발 모드
```
KIWOOM_MODE=mock
EXECUTION_ENABLED=true
APPROVAL_MODE=auto
```
- 실제 서버 호출 안 함
- 전체 파이프라인 검증 가능

### 실전 수동 승인 모드
```
KIWOOM_MODE=real
EXECUTION_ENABLED=true
APPROVAL_MODE=manual
```
- 승인 후에만 주문 실행

### 실전 자동 모드 (주의)
```
KIWOOM_MODE=real
EXECUTION_ENABLED=true
APPROVAL_MODE=auto
```
- 완전 자동 매매

---

## 4. Intent 상태 흐름

stored → approved → executed
stored → rejected

최근주문 조회 시 상태 포함 출력

---

## 5. 스크립트와 테스트의 역할 분리

### pytest
- 구조 검증
- Guard 동작 확인
- Intent 상태 전이 검증

### scripts
- 실제 API 스펙 검증
- 필수 파라미터 확인
- 서버 제한(429 등) 확인

실 API는 테스트 더블로 완벽히 재현 불가 → 반드시 script 병행 필요

---

## 6. 다음 단계 로드맵

1) Strategy / Scanner / Monitor 모듈 분리
2) Risk Engine 강화 (손절/포지션 한도)
3) 로그 → 리포트 자동화
4) 실전 모드 점진 전환

---

이 문서는 M14 이후 구조를 빠르게 이해하기 위한 요약 문서이다.
