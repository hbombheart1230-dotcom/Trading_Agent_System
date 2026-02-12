# Composite Skills 설계

## 개념 정의
Composite Skill은 여러 개의 Raw API(api_id)를 조합하여
에이전트가 직접 사용할 수 있는 **의미 단위 동작**을 제공합니다.

에이전트는 절대 개별 api_id를 알지 않습니다.

---

## 1. 인증 / 세션

### auth.issue_token
- 설명: 키움 REST 접근 토큰 발급
- Raw api_id:
  - au10001

### auth.revoke_token
- 설명: 토큰 폐기
- Raw api_id:
  - au10002

---

## 2. 계좌(Account)

### account.snapshot
- 설명: 현재 계좌 상태의 단일 스냅샷
- 포함 정보:
  - 예수금 / D+예수금
  - 보유 종목
  - 미체결 주문
- Raw api_id (예시):
  - 잔고 조회
  - 보유 종목 조회
  - 미체결 조회

> 주의:
> - 여러 api_id 호출 결과를 **하나의 AccountSnapshot DTO**로 병합
> - Supervisor와 Monitor는 이 결과만 사용

---

## 3. 종목/시장(Market)

### market.quote(symbol)
- 설명: 종목의 현재 상태 요약
- 포함:
  - 현재가
  - 전일대비
  - 거래량 / 거래대금
  - 호가 요약
- Raw api_id:
  - 현재가 조회
  - 호가 조회

### market.candles(symbol, timeframe)
- 설명: 분봉/일봉 캔들 데이터
- Raw api_id:
  - 분봉 조회
  - 일봉 조회

---

## 4. 유니버스(Universe)

### universe.condition_list
- 설명: 조건검색 목록 조회
- Raw api_id:
  - 조건검색 목록

### universe.condition_search(condition_id)
- 설명: 조건검색 실행
- Raw api_id:
  - 조건검색 실행

---

## 5. 주문(Order)

### order.place(order_intent)
- 설명: 감독관 승인 후 주문 실행
- Raw api_id:
  - 주문 실행

### order.status(order_id)
- 설명: 주문 상태 조회
- Raw api_id:
  - 주문 조회

### order.cancel(order_id)
- 설명: 미체결 주문 취소
- Raw api_id:
  - 주문 취소

---

## 설계 원칙 요약
- Composite Skill은 **의미 단위**
- Raw API 변화는 Composite Skill 내부에서 흡수
- 에이전트 계약(IO)은 절대 깨지지 않게 유지
