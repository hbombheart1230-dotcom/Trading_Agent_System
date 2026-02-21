# M19-4: OpenRouter 기반 뉴스 감성(호재/악재) 스코어러

## 목표
- **네이버 뉴스 수집 결과**를 기반으로 종목별 뉴스 감성 점수(sentiment)를 산출한다.
- LLM 호출은 **OpenRouter**를 사용하되, 향후 사내/다른 LLM로 교체 가능하도록 **모듈화**한다.

## 핵심 변경점
### 1) LLM 호출 레이어 분리
- `libs/llm/openrouter_client.py` : OpenRouter Chat Completions HTTP 클라이언트
- `libs/llm/llm_router.py` : Role(에이전트) -> Model 라우팅
  - 역할별 모델을 env로 분리할 수 있다.

### 2) News Sentiment Scorer 플러그인
- `libs/news/scorers/llm.py`
  - `news_scorer=openrouter`일 때 종목별 뉴스 감성을 LLM으로 추정
  - 안전 장치:
    - `state['mock_news_sentiment']`가 있으면 **항상 mock 사용**
    - `DRY_RUN=1` 또는 `OPENROUTER_API_KEY` 미설정이면 **0.0 반환(네트워크 미호출)**

### 3) Pipeline 계약 고정
- `libs/news/news_pipeline.py`
  - `collect_news_items(symbols, state, policy) -> dict[symbol, list[NewsItem]]`
  - `score_news_sentiment(items_by_symbol, state, policy) -> dict[symbol, float]`

## 사용 방법
### policy 예시
```python
policy = {
  "news_provider": "naver",          # M19-1 네이버 API
  "news_scorer": "openrouter",      # M19-4 LLM scorer
  "news_topn_per_symbol": 5,
  "news_llm_role": "NEWS_SCORER",
  "news_llm_temperature": 0.0,
  "news_llm_max_tokens": 64,
}
```

### env 예시 (추가)
`config/.env.example` 참고

## 테스트
- `tests/test_m19_4_openrouter_news_scorer.py`
  - DRY_RUN에서 mock/default 동작 검증
