# M19-2 Global Sentiment 실측 강화

## 목표
Strategist가 사용하는 `global_sentiment`를 **실제 시장 지표 기반**으로 계산한다.
- 출력: `[-1.0, +1.0]` (risk-off ~ risk-on)
- 실패/예외 시: `0.0` (중립)으로 안전하게 fallback

## 우선순위 규칙
1. `state["mock_global_sentiment"]`가 있으면 그 값을 사용 (테스트/주입)
2. `DRY_RUN=1`이면 네트워크 호출 없이 `0.0`
3. LIVE(best-effort): `yfinance`가 설치되어 있으면 지표를 가져와 계산
   - `yfinance` 미설치/네트워크 오류/데이터 부족이면 `0.0`

## 사용 지표 (기본)
- S&P500: `^GSPC` (1일 수익률)
- NASDAQ: `^IXIC` (1일 수익률)
- 달러인덱스: `DX-Y.NYB` (1일 수익률)
- 미국 10년물 금리: `^TNX` (전일 대비 변화량, 대략 %p)

## 계산식 (raw)
```text
raw = 0.4 * sp500_return
    + 0.4 * nasdaq_return
    - 0.1 * dxy_return
    - 0.1 * tnx_delta
```
정규화는 `tanh(scale * raw)`를 사용하여 `[-1, +1]`로 매핑한다.
- 기본 `scale = 5.0`

## Policy 키
`policy`에 아래 키를 넣어 계산 방식을 바꿀 수 있다.

- `sentiment_weights` (dict)
  - `sp500` (default 0.4)
  - `nasdaq` (default 0.4)
  - `dxy` (default 0.1)
  - `tnx` (default 0.1)
- `sentiment_norm` (dict)
  - `scale` (default 5.0)
- ticker override
  - `sentiment_ticker_sp500` (default `^GSPC`)
  - `sentiment_ticker_nasdaq` (default `^IXIC`)
  - `sentiment_ticker_dxy` (default `DX-Y.NYB`)
  - `sentiment_ticker_tnx` (default `^TNX`)

## 상태(state) 반영
Strategist는 계산된 값을 다음 형태로 남긴다(기존 M18-3 계약 유지).
- `state["global_sentiment"] = float`
- `state["policy"]["global_sentiment"] = float` (추적/디버깅용)

## 운영 팁
- 회사/폐쇄망 환경에서 `yfinance` 설치가 어렵거나 네트워크가 불안정하면,
  초기에는 `mock_global_sentiment` 주입으로만 검증하고,
  운영 단계에서만 `yfinance`를 켜는 것을 권장한다.
