# Kiwoom Scanner / Strategist Inventory

## 목적

Kiwoom API 정렬 작업에서는 아래 두 축을 분리해서 본다.

1. scanner가 지금 실제로 쓰는 Kiwoom source
2. strategist가 추가로 가져올 수 있는 Kiwoom source

원칙:
- scanner는 후보 풀, 유동성, intraday heat, opening strength 중심이다.
- strategist는 regime, sector, flow, carry review 중심이다.
- 조건검색은 Kiwoom catalog에는 있지만 모의투자 미지원이라 실전 scanner source에서는 제외한다.

## 1. Scanner가 지금 실제로 쓰는 Kiwoom source

### A. candidate pool ranking

코드:
- `libs/strategies/candidates/kiwoom_candidate_provider.py`
- `libs/read/kiwoom_rank_reader.py`

실제 사용 API:
- `ka10030`
  - 거래량 / 거래대금 상위
- `ka10027`
  - 등락률 상위

현재 scanner candidate source:
1. 거래량 상위
2. 거래대금 상위
3. 등락률 상위
4. sector/theme map
5. operator watchlist

중요:
- 조건검색은 현재 scanner source에서 의도적으로 제외한다.
- 이유는 모의투자 미지원이고, 실전과 모의의 source 구성이 달라지는 것을 피하려는 것이다.

### B. condition search

코드:
- `libs/read/kiwoom_condition_reader.py`

현재 상태:
- reader는 존재한다.
- mock/env fallback 위주다.
- 실전 scanner source로는 채택하지 않는다.

catalog reference:
- `ka10171`
  - 조건검색 목록조회
- `ka10172`
  - 조건검색 요청 일반
- `ka10173`
  - 조건검색 요청 실시간
- `ka10174`
  - 조건검색 실시간 해제

즉 condition search는 catalog reference로만 유지하고, 현재 live scanner source에서는 쓰지 않는다.

### C. quote hydration

코드:
- `config/skills/market.quote.yaml`
- `graphs/nodes/hydrate_skill_results_node.py`
- `graphs/nodes/skill_contracts.py`

실제 사용 API:
- `ka10003`
  - 체결정보요청

현재 추출 값:
- `symbol`
- `cur` / `price`
- `best_bid`
- `best_ask`
- 누적 거래량 / 거래대금 계열 raw field

역할:
- execution quote snapshot
- spread 계산
- liquidity / practical filter 보강

### D. minute OHLCV

코드:
- `config/skills/market.minute_ohlcv.yaml`
- `graphs/nodes/monitor_node.py`
- `graphs/nodes/skill_contracts.py`
- `libs/skills/dto_extractors.py`

실제 사용 API:
- `ka10080`
  - minute OHLCV source

현재 추출 값:
- `open`
- `high`
- `low`
- `close`
- `volume`
- `ts`

중요:
- 이 값은 scanner보다 monitor entry confirmation에서 더 직접적이다.
- scanner에서는 candidate pool / feature hydration에서 간접 사용한다.

## 2. Scanner에 추가 가능한 Kiwoom source 후보

### 바로 가치가 큰 후보

1. `ka10023`
- 거래량 급증
- breakout / reclaim prior 강화

2. `ka10019`
- 가격 급등락
- momentum 과열 / 급변 분리

3. `ka10028`
- 시가대비등락률
- open drive 강도 확인

4. `ka10029`
- 예상체결등락률
- preopen / opening auction prior

5. `ka00198`
- 실시간종목조회순위
- intraday heat map 보강

### scanner에 붙일 때 주의할 점

- source를 많이 붙인다고 좋은 게 아니다.
- 후보 noise와 중복 score가 먼저 늘어난다.
- 추천 순서:
  1. `ka10023`
  2. `ka10028`
  3. `ka10029`
  4. `ka00198`

## 3. Strategist가 지금 직접 쓰는 Kiwoom source

정확히 말하면 거의 없다.

코드:
- `graphs/nodes/strategist_node.py`

현재 strategist hot path 입력:
- `market_context_inputs`
- `global_sentiment_signal`
- `news_context`
- `candidate_symbols_hint`
- `read_model_facts`
- `recent_strategy_feedback`
- `reporter_feedback_packet`
- `strategy_memory`
- `commander_refresh_context`

즉 strategist는 지금
- 뉴스
- memory packet
- candidate hints
- commander refresh context
를 주로 쓴다.

Kiwoom 직접 fetch는 strategist node에 아직 없다.

## 4. Strategist에 추가 가능한 Kiwoom source 후보

strategist는 per-symbol micro tick보다 regime / sector / flow / carry-risk source가 맞다.

### A. market / regime packet

1. `0U`
- 업종등락 websocket
- sector breadth / rotation

2. `ka10010`
- 업종프로그램요청
- 업종 단위 risk-on / risk-off 확인

3. `ka90001`
- 테마그룹별요청
- 오늘 강한 테마 / 약한 테마 확인

### B. flow packet

4. `ka10008`
- 외국인 수급

5. `ka10009`
- 기관 수급

6. `ka10013`
- 신용매매 동향

7. `ka10014`
- 공매도 추이

### C. carry / selected-symbol review packet

8. `ka10001`
- selected symbol 기본정보 보강

9. `ka10004`
- selected symbol 호가 quality

10. `ka10005` / `ka10006` / `ka10080`
- 장초반 recovery / VWAP reclaim / minute 상태 판단

### D. account / carry truth packet

11. `kt00018`
- 보유 종목, 평균단가, 미실현손익

12. `ka01690`
- 일별 잔고 수익률

## 5. Strategist에 붙일 때 원칙

붙여야 하는 것:
- sector breadth
- theme strength
- foreign / institution flow
- carry position truth
- session-open recovery quality

붙이지 말아야 하는 것:
- noisy micro tick raw feed를 prompt에 그대로 넣는 것
- scanner rank source를 strategist에 그대로 복사하는 것
- monitor execution trigger를 strategist broad frame에 섞는 것
