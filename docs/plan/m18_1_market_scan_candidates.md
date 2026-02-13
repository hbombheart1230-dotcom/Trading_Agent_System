# M18-1 Strategist 후보 생성: Market Scan

## 목표
- 사용자가 직접 종목을 고르지 않고, Strategist가 **시장 자동 스캔**으로 3~5 후보를 만든다.
- DRY_RUN/테스트 환경에서는 네트워크 없이도 동일한 결과를 재현할 수 있어야 한다.

## 후보 생성 우선순위(주입 → 자동)
1. `state["candidates"]`가 이미 있으면 그대로 사용(상위 플로우 주입)
2. `state["candidate_symbols"]`가 있으면 top-k로 후보 생성
3. `state["universe"]`가 있으면 앞에서 top-k 사용(테스트 호환)
4. 그 외 → `candidate_source`에 따라 자동 생성
   - `top_picks`(기본): 랭킹 + 조건검색식 조합
   - `market_rank`: 랭킹 API 단독

## 정책 키(예)
- `candidate_k`: 후보 개수(기본 5)
- `candidate_source`: `top_picks | market_rank`
- `candidate_rank_mode`: `value|volume|change` 등
- `candidate_rank_topn`: 랭킹 상위 N
- `candidate_topk`: 최종 후보 K

## DRY_RUN 전략
- `DRY_RUN=1` 또는 테스트에서는 `mock_rank_symbols`, `mock_condition_symbols` 등의 state 주입을 우선 사용.
- 네트워크 호출은 best-effort이며 실패 시에도 후보가 0개가 되지 않도록 fallback을 둔다.

## 출력
- `state["candidates"] = [{"symbol": "...", "why": "market_rank|top_picks"}, ...]`
