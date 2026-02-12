# M9 – Read Layer 표준화 (FINAL)

## 목적
M9의 목표는 **전략 · 감독관 · 실행기**가 공통으로 사용하는  
**판단 입력용 Read-only Snapshot**을 표준화하는 것이다.

- 원본 API 응답 ❌
- 거래 로그 ❌
- 판단에 필요한 최소 상태 요약 ⭕
- 기본 동작: **real HTTP + KIWOOM_MODE=mock**

---

## Snapshot 정의

### MarketSnapshot (현재가 기준)
```json
{
  "symbol": "005930",
  "price": 71200,
  "ts": 1700000000
}
```

### PortfolioSnapshot
```json
{
  "cash": 10000000,
  "positions": [
    {
      "symbol": "005930",
      "qty": 10,
      "avg_price": 70000,
      "unrealized_pnl": 12000
    }
  ]
}
```

---

## 구성 요약

### Reader
- Mock Reader: 테스트/단위 검증 전용
- Real Reader:
  - 가격: ka10001 (주식기본정보요청)
  - 포트폴리오: 계좌 잔고 + 보유 종목 요약
  - mock 모드에서도 **실제 HTTP 호출**

### Node
- build_market_snapshot
- build_portfolio_snapshot
- build_snapshots (aggregation)

```python
state["snapshots"] = {
  "market": market_snapshot,
  "portfolio": portfolio_snapshot
}
```

---

## 로그 정책
- Snapshot 생성 자체는 로그 ❌
- 이유:
  - polling 기반, 빈번한 호출
  - 상태 입력 데이터이기 때문
- 이후 단계(M10 risk_context, execution)부터 로그 ⭕

---

## M9 완료 조건
- 파이프라인은 항상 `state["snapshots"]`를 제공
- M10 risk_context 계산의 입력으로 사용
