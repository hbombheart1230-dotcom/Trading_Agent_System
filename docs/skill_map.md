# Composite Skill 매핑표 (Skill → DTO → api_id)

이 문서는 Composite Skill이
- 어떤 Raw API(api_id)를 호출하고
- 어떤 DTO 필드를 채우는지
를 명확히 정의합니다.

---

## 1) auth.issue_token
- 사용 DTO: 없음 (토큰 캐시 갱신)
- Raw api_id:
  - au10001

## 2) auth.revoke_token
- 사용 DTO: 없음
- Raw api_id:
  - au10002

---

## 3) account.snapshot
- 출력 DTO: AccountSnapshot

### Raw api_id (예시)
- 계좌 잔고 조회
- 보유 종목 조회
- 미체결 주문 조회

### DTO 필드 매핑
- `cash_available` ← 예수금
- `positions[].symbol` ← 종목코드
- `positions[].qty` ← 보유수량
- `positions[].avg_price` ← 평균단가
- `open_orders[].order_id` ← 주문번호
- 기타 미정 필드 → `extra` 또는 `raw`

---

## 4) market.quote(symbol)
- 출력 DTO: MarketSnapshot

### Raw api_id
- 현재가 조회
- 호가 조회 (요약)

### DTO 필드 매핑
- `price` ← 현재가
- `change` ← 전일대비
- `change_pct` ← 등락률
- `volume` ← 거래량
- `value` ← 거래대금

---

## 5) market.candles(symbol, timeframe)
- 출력 DTO: CandleSeries

### Raw api_id
- 분봉 조회
- 일봉 조회

### DTO 필드 매핑
- `candles[].o/h/l/c` ← 시가/고가/저가/종가
- `candles[].v` ← 거래량

---

## 6) universe.condition_list
- 출력 DTO: (간단 목록 DTO 또는 raw)

### Raw api_id
- 조건검색 목록 조회

---

## 7) universe.condition_search(condition_id)
- 출력 DTO: UniverseResult

### Raw api_id
- 조건검색 실행

### DTO 필드 매핑
- `items[].symbol` ← 종목코드
- `items[].rank` ← 순위 (가능 시)

---

## 8) order.place(order_intent)
- 출력 DTO: OrderResult

### Raw api_id
- 주문 실행

### DTO 필드 매핑
- `order_id` ← 주문번호
- `accepted` ← 접수 여부

---

## 9) order.status(order_id)
- 출력 DTO: OrderStatus

### Raw api_id
- 주문 조회

---

## 10) order.cancel(order_id)
- 출력 DTO: OrderResult

### Raw api_id
- 주문 취소

---

## 설계 메모
- Raw api_id 정확한 목록은 구현 시 `registry.md` 기준으로 확정
- DTO 필드에 매핑되지 않는 값은 **버리지 말고 raw/extra에 보관**
- Reporter는 DTO만 참조 (raw 직접 접근 금지)
