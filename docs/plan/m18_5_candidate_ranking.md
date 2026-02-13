# M18-5 Strategist Candidate Ranking

## 목적
Strategist는 **사용자 수동 선택 없이** 시장 스캔 결과로 3~5개 후보를 생성한다.
M18-5에서는 후보 생성 이후, 다음 신호로 후보 **우선순위를 재정렬**한다.

- Global Sentiment (risk-on / risk-off)
- News Sentiment (호재/악재 점수)

> 원칙: Strategist는 **신호 수집/정책 결정/후보 우선순위**만 담당한다.  
> 수치 계산과 최종 선정은 Scanner가 담당한다.

---

## 입력 신호

### Global Sentiment
- 범위: `[-1.0, +1.0]`
- source 예시: 미국장 종가/환율/국채금리 (yfinance)

### News Sentiment
- 범위: `[-1.0, +1.0]`
- source 예시: Naver/Google News 수집 → LLM 분류/점수화

---

## 후보 재정렬 규칙 (M18-5)

후보 리스트의 기존 순서(거래대금/거래량/등락률 랭킹)를 `rank_score`로 사용한다.

- `rank_score = (N - idx) / N`  (idx=0이 최고)
- `candidate_score = rank_score + w_news * news + w_global * global`

정렬: `candidate_score` 내림차순.

### 음수 뉴스 필터 (옵션)
`news_sentiment < candidate_negative_news_threshold` 후보는 제외하되,
최소 3개 후보는 유지하도록 (3개 미만이면 필터 무시)

---

## Risk-off 시 후보 수 축소
`global_sentiment <= candidate_risk_off_threshold`일 때,
`candidate_max_count_risk_off`(기본 3)개로 후보 수를 줄인다.

---

## Policy Keys

| key | default | 설명 |
|---|---:|---|
| candidate_news_weight | 0.25 | 뉴스 점수 가중치 |
| candidate_global_weight | 0.10 | 글로벌 센티 가중치 |
| candidate_negative_news_threshold | -0.7 | 악재 필터 임계치 |
| candidate_risk_off_threshold | -0.6 | Risk-off 판단 임계치 |
| candidate_max_count_risk_off | 3 | Risk-off일 때 후보 최대 개수 |

---

## 테스트 주입 포인트
- `mock_global_sentiment`
- `mock_news_sentiment`
- `mock_rank_symbols`, `mock_condition_symbols` (Top Picks 생성 테스트용)
