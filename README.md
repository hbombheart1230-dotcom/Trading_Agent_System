# 키움 Agentic Trading System — Design-First README

> **이 README 하나만 읽어도 전체 그림이 보이도록 정리된 문서**  
> (철학 · 설계 원칙 · 아키텍처 · 데이터 흐름 · 확장 전략)

---

## 0. 한 줄 요약
**판단은 AI가, 실행은 시스템이, 주문은 감독관 승인 후에만.**  
AI 지능이 발전할수록 자동으로 성능이 함께 성장하는 트레이딩 시스템.

---

## 1. 왜 이 시스템을 만드는가 (철학)

### 1.1 문제 정의
- 키움 REST API는 200+ 개로 방대함
- 사람이 지표/시간/뉴스를 고정하면 **AI 발전을 가로막는 구조**가 됨
- 코드 중심 설계는 변경 비용이 커서 장기 운영에 취약

### 1.2 해결 전략
- **Design-first**: 코드보다 계약과 구조를 먼저 고정
- **AI 자율 판단**: 무엇을 볼지/언제 볼지/뉴스를 볼지 AI가 결정
- **정확한 실행**: API 호출·수치 산출은 스킬이 정확히 수행
- **안전 장치**: 주문은 항상 감독관 승인(2-phase commit)

> 핵심 신념: **AI 지능은 교체 가능, 실행 신뢰성은 불변**

---

## 2. 핵심 원칙 (절대 불변)

1. **주문 2단계 커밋**
   - OrderIntent → Supervisor 승인 → Execution
2. **단일 진실**
   - API 스펙: JSONL Registry
   - 상태: TradeState
3. **역할 분리**
   - 에이전트는 판단만, 스킬은 실행만
4. **재현 가능성**
   - 모든 판단/호출/승인을 EventLog로 기록

---

## 3. 전체 아키텍처 개요

```
[ Strategist ]  →  TradePlan
       ↓
[ Scanner ]     →  ScanResult
       ↓
[ Monitor ]     →  OrderIntent
       ↓
[ Supervisor ]  →  Approve / Reject / Modify
       ↓
[ Execution ]   →  Raw Kiwoom API
```

### 에이전트 구성
- **Supervisor(감독관)**: 정책·리스크·최종 승인
- **Strategist(전략가)**: 무엇을 볼지 결정
- **Scanner(스캐너)**: 데이터 수집·지표 계산
- **Monitor(모니터)**: 실시간 감시·주문 의도 생성
- **Reporter(리포터)**: 로그 재생·회고·개선 제안

---

## 4. 데이터 계층 구조

```
Agent 판단
   ↓
Composite Skill (의미 단위)
   ↓
DTO (표준 데이터 모델)
   ↓
ApiSpec (JSONL Registry)
   ↓
Raw Kiwoom REST API
```

- 에이전트는 **api_id를 모름**
- API 변경은 Composite Skill 내부에서만 흡수

---

## 5. API Registry (JSONL)

### 소스
- `kiwoom_api_list_tagged.jsonl`
- `kiwoom_apis.jsonl`

### 규칙
- **유일 식별자: api_id**
- endpoint 중복은 정상
- `api_id="공통"(오류코드)`는 호출 불가(catalog)

### 내부 표준: ApiSpec
- request/response를 FieldSpec으로 표준화
- cont-yn / next-key는 런타임 공통 페이징 처리

---

## 6. Composite Skill (도메인 동작)

대표 예시:
- `account.snapshot`
- `market.quote(symbol)`
- `market.candles(symbol, timeframe)`
- `universe.condition_search`
- `order.place / status / cancel`

> Composite Skill은 **에이전트가 사용하는 최상위 실행 인터페이스**

---

## 7. DTO (표준 출력 모델)

핵심 DTO:
- `AccountSnapshot`
- `MarketSnapshot`
- `CandleSeries`
- `UniverseResult`
- `OrderResult / OrderStatus`

공통 규칙:
- `ts` (KST ISO8601) 필수
- `raw` / `extra`로 미래 확장 허용

---

## 8. IO 계약 (에이전트 통신)

고정 JSON 계약:
- `RunConfig`
- `TradePlan`
- `ScanResult`
- `OrderIntent`
- `SupervisorDecision`

> AI 프롬프트·테스트·리플레이가 쉬워짐

---

## 9. 런타임 상태 & 로그

### TradeState
- 계좌/포지션/전략/스캔 결과/감시 대상

### EventLog
- 에이전트 판단
- API 호출
- 승인 이력
- 오류

**목표: 모든 실행을 다시 재생 가능**

---

## 10. 환경 변수(.env)

env는 설정이 아니라 **운영 정책**이다.
- mock / real 완전 분리
- 리스크 한도는 Supervisor가 강제 집행
- 주문 기본값(limit/IOC 등)을 중앙 통제

---

## 11. 미래 확장 전략 (중요)

이 설계는 **AI 지능 상승을 전제로** 한다.

- AI가 선택하는 지표/시간/뉴스는 계속 변화 가능
- 스킬/DTO/계약은 유지 → 코드 변경 최소
- 승인 정책도 점진적으로 자동화 가능

> 지금은 보수적으로, 미래에는 자율적으로.

---

## 12. 이 README의 역할

- 이 프로젝트의 **헌법**
- 6개월 뒤 다시 봐도 전체 구조 복원 가능
- 코드가 바뀌어도 이 문서는 살아남아야 함

---

### 마지막 문장
**"AI를 믿되, 시스템은 의심하라."**
