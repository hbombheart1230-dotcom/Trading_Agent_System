# DTO(표준 데이터 모델) 설계

이 문서는 **Composite Skill의 출력 형태를 표준화**합니다.
에이전트는 Raw API 응답이 아니라 DTO만 봅니다.

## 설계 원칙
1) **핵심 필드 최소 고정**: 모든 구현이 반드시 제공
2) **확장 필드 허용**: `extra`/`raw`로 언제든 확장
3) **타임스탬프 필수**: 재현/디버깅을 위해
4) **통화/단위 명시**: KRW, 주식 수량, 퍼센트 등 혼동 방지

---

## 1) 공통 베이스: BaseDTO
모든 DTO는 아래 공통 필드를 포함합니다.

- `ts` : ISO8601 (KST) — 데이터 스냅샷 시각
- `source` : "kiwoom" | "derived" | "mixed"
- `mode` : "mock" | "real"
- `raw` : (선택) 원본 응답 저장용
- `extra` : (선택) 확장 필드 저장용

---

## 2) AccountSnapshot (account.snapshot 출력)

### 필수 필드
- `ts`
- `cash_available` : number (KRW)
- `cash_total` : number (KRW)  (가능하면)
- `positions[]` :
  - `symbol` : string
  - `name` : string (가능하면)
  - `qty` : number
  - `avg_price` : number (KRW)
  - `market_price` : number (KRW) (가능하면)
  - `pnl` : number (KRW) (가능하면)
  - `pnl_pct` : number (가능하면)
- `open_orders[]` :
  - `order_id` : string
  - `symbol` : string
  - `side` : "buy"|"sell"
  - `qty` : number
  - `filled_qty` : number
  - `price` : number (KRW)
  - `status` : string
  - `created_at` : ISO8601 (가능하면)

### 확장(선택)
- `d_plus_cash` : number
- `margin` 관련
- `account_metrics` : object

---

## 3) MarketSnapshot (market.quote 출력)

### 필수 필드
- `ts`
- `symbol`
- `price` : number (KRW)
- `change` : number (KRW)
- `change_pct` : number
- `volume` : number
- `value` : number (거래대금, KRW)

### 확장(선택)
- `bid`/`ask` 요약
- `orderbook` (5~10호가)
- `halted` (거래정지/VI 등)
- `market_flags`

---

## 4) CandleSeries (market.candles 출력)

### 필수 필드
- `ts`
- `symbol`
- `timeframe` : "1m"|"3m"|"5m"|"15m"|"1h"|"1d" 등
- `candles[]` :
  - `t` : ISO8601 또는 epoch
  - `o` : number
  - `h` : number
  - `l` : number
  - `c` : number
  - `v` : number
  - `value` : number (가능하면)

### 확장(선택)
- `timezone`
- `adjusted` (수정주가 여부)

---

## 5) UniverseResult (universe.condition_search 출력)

### 필수 필드
- `ts`
- `condition_id`
- `items[]` :
  - `symbol`
  - `name` (가능하면)
  - `rank` (가능하면)
  - `reason` (가능하면)

### 확장(선택)
- `raw_count`
- `paging` 정보

---

## 6) OrderResult / OrderStatus (order.place, order.status 출력)

### OrderResult (place)
- `ts`
- `intent_id`
- `order_id`
- `symbol`
- `side`
- `requested_qty`
- `requested_price`
- `accepted` : boolean
- `message` : string (가능하면)

### OrderStatus (status)
- `ts`
- `order_id`
- `symbol`
- `side`
- `qty`
- `filled_qty`
- `avg_fill_price` (가능하면)
- `status`
- `last_update_at` (가능하면)

---

## 7) FeaturePack (scanner.calc_features 출력, 선택)

### 필수 필드
- `ts`
- `symbol`
- `features` : object  (key=value, 예: volatility_20d, gap_pct ...)

### 확장(선택)
- `feature_defs` : object (단위/설명)
- `inputs` : object (계산에 사용한 원 데이터 참조)

---

## 권장 구현 메모
- DTO는 Pydantic 모델로 만들되, `extra`/`raw`로 미래 확장을 흡수
- Reporter는 DTO만 읽도록 강제(원본 응답 직접 참조 금지)
