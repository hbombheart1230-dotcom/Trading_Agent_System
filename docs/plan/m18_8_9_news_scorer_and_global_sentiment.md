# M18-8 / M18-9: News Scorer 플러그인 + Global Sentiment 실제 계산기

## 목적
- News Analysis를 **Provider(수집)** 와 **Scorer(점수화)** 로 분리하여 확장 가능하게 한다.
- Global Sentiment는 `mock_global_sentiment` 주입으로 테스트 가능하며,
  LIVE에서는 `yfinance` 기반으로 **best-effort** 계산이 가능하도록 “자리”를 만든다.

## News 구성
- Provider: `libs/news/providers/*`
- Scorer: `libs/news/scorers/*`
- Pipeline: `libs/news/news_pipeline.py`

### Policy 키
- `news_provider`: `naver` | `google_news` | (추후 확장)
- `news_scorer`: `simple` | `llm` | (추후 확장)
- `use_news_analysis`: true/false

### 주입(테스트/DRY_RUN)
- `mock_news_items`: NewsItem 리스트
- `mock_news_sentiment`: `{symbol: score}` (스코어러 우회)

## Global Sentiment 구성
- `libs/market/global_sentiment.py::compute_global_sentiment`

### Policy 키
- `use_global_sentiment`: true/false
- `gs_ticker_spx`, `gs_ticker_ndx`, `gs_ticker_usdkrw` (LIVE에서만 사용)

### 주입(테스트/DRY_RUN)
- `mock_global_sentiment`: [-1, +1]

## Strategist 연결
- `graphs/nodes/strategist_node.py`에서:
  - candidates 생성
  - global_sentiment 계산 후 `policy["global_sentiment"]`에 기록
  - news_pipeline으로 `news_items`/`news_sentiment` 생성
  - 후보 rerank에 반영(M18-5 유지)
