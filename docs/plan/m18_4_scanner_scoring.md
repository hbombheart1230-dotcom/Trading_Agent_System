# M18-4: Scanner scoring에 Sentiment 반영

## 목적

Strategist가 수집/첨부하는 신호(Global Sentiment, News Sentiment)를 **Scanner의 score/risk/confidence** 계산에 반영하여,
후보 선정이 "상황/뉴스"에 의해 자동으로 바뀌도록 만든다.

## 책임 분리

| Agent | 책임 |
|---|---|
| Strategist | 후보(3~5) 생성 + 신호(Global/News) 수집/첨부 + 정책(policy) 설정 |
| Scanner | 후보별 feature/score/risk/confidence 계산 (이 문서의 핵심) |
| Monitor | 최종 1개에 대해 OrderIntent만 생성 |

## 입력

Scanner는 아래 입력을 **있으면 사용**, 없으면 0으로 간주한다.

- Global Sentiment: `state.mock_global_sentiment` 또는 `state.global_sentiment.score` 또는 `state.policy.global_sentiment.score`
  - 범위: `[-1, +1]` (risk-off=-1, risk-on=+1)
- News Sentiment: `state.news_sentiment[symbol]` 또는 `state.mock_news_sentiment[symbol]`
  - 범위: `[-1, +1]` (악재=-1, 호재=+1)

## 가중치 정책 (policy)

Scanner에서 사용하는 기본 키:

```yaml
weight_news: 0.20
weight_global: 0.10
risk_news_penalty: 0.30
risk_global_penalty: 0.20
confidence_news_boost: 0.05
```

## 계산식

`base_*`는 기존 스캐너가 계산하던 값(또는 테스트 주입값)이다.

```text
adj_score = base_score + weight_news * news + weight_global * global

adj_risk  = base_risk
          + risk_news_penalty   * max(-news,   0)
          + risk_global_penalty * max(-global, 0)

adj_confidence = clamp(base_confidence + confidence_news_boost * max(news, 0), 0, 1)
```

## 출력

Scanner는 최종값을 `row.score`, `row.risk_score`, `row.confidence`에 반영하고,
디버그를 위해 `row.components`에 base와 가중치를 기록한다.

## 테스트

- 뉴스 호재가 점수를 올려 최종 선정(top1)을 바꾸는지
- risk-off(global<0)에서 risk_score가 증가하는지
