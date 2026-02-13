# M18 Strategist Signals (확장 계획)

이 문서는 Strategist가 '후보 종목(3~5)'과 '정책(policy)'을 만들기 위해 참고하는 입력 신호들을 정의한다.

## 1) Global Sentiment (시장 분위기)
- 소스: yfinance 등(미장 지수/환율/국채금리)
- 목적: 오늘이 **Risk-on / Risk-off**인지 판단해서 `policy`를 보수적으로/공격적으로 조정
- 출력(정규화): `global_sentiment.score` ∈ [-1.0, +1.0]
  - -1: 강한 Risk-off (보수적)
  - +1: 강한 Risk-on (공격적)

### 정책 반영(초기 룰)
- Risk-off(음수): `max_risk` ↓, `min_confidence` ↑
- Risk-on(양수): `max_risk` ↑, `min_confidence` ↓
- 구현: `libs/market/global_sentiment.py`

## 2) Top Picks (시장 자동 스캔 후보)
- 소스: PyKRX / Kiwoom API
  - 전일/당일 거래대금/거래량/등락률 랭킹
  - 조건검색식 결과(있으면) 필터
- 목적: 사용자의 수동 지정 없이도 **후보를 자동 생성**

## 3) News Analysis (뉴스 기반 호재/악재 점수)
- 소스: Naver API / Google News
- 목적: 후보별 뉴스 흐름을 수집해서 LLM으로 **호재/악재 점수화**
- 출력(정규화): `news_sentiment[symbol]` ∈ [-1.0, +1.0]
  - -1: 악재 우세
  - +1: 호재 우세
- 구현(스텁): `libs/news/news_analyzer.py`
  - 테스트/DRY_RUN에서는 `state["mock_news_sentiment"]`로 주입해 검증
  - 라이브에선 뉴스 수집/LLM 연결만 교체(호출부 유지)

## 4) 단계별 적용 로드맵
- M18-2: Top Picks 후보 생성
- M18-3: Global Sentiment + News Analysis를 Strategist 출력에 포함
- M18-4+: Scanner scoring에 `news_sentiment`, `global_sentiment`를 반영(가중치/정책 튜닝)
