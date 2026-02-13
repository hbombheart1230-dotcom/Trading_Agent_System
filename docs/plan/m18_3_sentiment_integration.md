# M18-3 Sentiment Integration (Global + News) - 초기 연결

## 목표
- Strategist가 시장 분위기(Global Sentiment)와 뉴스 분석(News Sentiment)을 **state/policy에 반영**한다.
- 실제 API 연결 전에도 mock/state 주입만으로 테스트가 가능해야 한다.

## Global Sentiment
### 입력
- 테스트/DRY_RUN: `state["mock_global_sentiment"]` ∈ [-1.0, +1.0]
- 출력(정책 기록): `policy["global_sentiment"] = value`

### 정책 자동 조정(개념)
- Risk-off(음수): `max_risk` ↓, `min_confidence` ↑
- Risk-on(양수): `max_risk` ↑, `min_confidence` ↓

> 실제 산출(yfinance 등)은 M18-8~9에서 플러그인 형태로 확장.

## News Sentiment
### 입력
- `state["mock_news_sentiment"] = {symbol: score}` 형태로 주입 가능
- 후보 심볼에 대해 값이 없으면 **0.0** 기본값 보장

### 출력
- `state["news_sentiment"] = {symbol: score}`

## 주의
- 기본 동작에서 불필요한 외부 호출이 발생하지 않도록
  - `use_news_analysis`가 꺼져있으면 Provider 호출을 하지 않는다.
  - 단, `mock_news_sentiment`가 존재하면 rerank/가중치는 적용 가능(테스트 용이).

## 테스트 포인트
- global_sentiment에 따라 정책 값이 변하는지(risk-on/risk-off)
- 후보에 없는 symbol은 news_sentiment가 0.0으로 채워지는지
