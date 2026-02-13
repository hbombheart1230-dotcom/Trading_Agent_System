# M18-6: News Collection Plugin (Strategist)

## 목표
- Strategist가 후보(3~5개)에 대해 뉴스 아이템을 수집하고, (추후) LLM으로 호재/악재 점수화할 수 있도록 **플러그인 인터페이스를 고정**한다.
- 초기 마일스톤에서는 **네트워크 호출을 강제하지 않는다**:
  - 테스트/DRY_RUN: `mock_news_items`, `mock_news_sentiment` 주입으로 재현 가능
  - LIVE 연결(M19+): Provider 구현만 교체/확장

## 구성요소
- `libs/news/providers/base.py`
  - `NewsItem`, `NewsProvider`(Protocol)
- `libs/news/providers/registry.py`
  - `NewsProviderRegistry`: policy 기반 provider 선택
- `libs/news/providers/naver.py`, `libs/news/providers/google_news.py`
  - 자리만 뚫어둔 provider 스텁(네트워크 미구현)
- `libs/news/news_pipeline.py`
  - `collect_news_items(symbols, ...)`
  - `score_news_sentiment_simple(items_by_symbol, ...)` (LLM 점수화 전 단계의 deterministic placeholder)

## 주입 포인트 (테스트/운영 공통)
- `state["mock_news_items"]`: `{symbol: [{title, published_at, source, url}...]}` 형태
- `state["mock_news_sentiment"]`: `{symbol: float}` 형태 ([-1, +1])
- `policy["news_provider"]`: `"naver" | "google_news" | ..."` (M19+에서 실제 provider 연결 시 사용)
- `policy["news_live"]` 또는 `NEWS_LIVE=1`: (M19+에서 네트워크 사용 허용)

## 다음 단계 (M19+)
- Naver Search API, Google News 등 실제 구현 연결
- LLM 기반 sentiment scorer 추가:
  - 뉴스 묶음 + 컨텍스트(시장/섹터/포지션) → score 산출
  - 캐싱/레이트리밋/중복 제거
