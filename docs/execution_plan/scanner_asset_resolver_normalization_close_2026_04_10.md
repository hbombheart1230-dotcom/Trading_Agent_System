# Scanner Asset Resolver Normalization Close (2026-04-10)

## Why this change was needed

`scanner` artifact에서 `selected_candidate.asset_class_detected` / `detection_source`가 `unknown` / `fallback`으로 많이 남아 있었습니다.
반면 `execute_from_packet` final guard는 ETF/ETN BUY 차단이 실제로 동작하고 있었기 때문에,
`scanner` 1차 분류와 final guard의 판별 기준이 어긋나 있는 상태였습니다.

이번 변경의 목적은 수익률 개선이나 entry tuning이 아니라,
`scanner`가 후보 종목을 얼마나 정확히 이해하고 있는지에 대한 관측성과 분류 일관성을 회복하는 것입니다.

## Resolver single-source principle

공식 자산 분류 resolver는 `libs/runtime/asset_universe_policy.py`의
`inspect_asset_universe_candidate(...)`와 `apply_asset_universe_filter(...)`입니다.

이번 변경으로:
- `scanner`는 `apply_asset_universe_filter(..., allow_remote_lookup=True)`를 사용
- `executor` final BUY guard는 같은 resolver 계열인 `inspect_asset_universe_candidate(..., allow_remote_lookup=True)`를 사용

즉 `scanner selected_candidate`와 `executor asset_universe_guard`가 가능한 한 동일한 기준으로
`asset_class_detected` / `detection_source`를 산출하도록 맞췄습니다.

## What changed

### 1. Blank field overwrite fix

기존에는 candidate row에 `asset_class_detected=""`, `detection_source=""`가 먼저 들어간 뒤
resolver 결과가 `setdefault(...)`로만 들어가면서, 빈 문자열이 그대로 남는 경로가 있었습니다.

이번에는 enrichment가 빈 값을 실제 resolver 결과로 덮어쓰도록 바꿨습니다.

### 2. Name heuristic expansion

ETF/ETN-family 판별에 다음 브랜드/표현을 강화했습니다.

- `KODEX`
- `TIGER`
- `KBSTAR`
- `ARIRANG`
- `HANARO`
- `SOL`
- `ACE`
- `KOSEF`
- `ETF`
- `ETN`
- `레버리지`
- `인버스`
- `액티브`
- `선물`
- `TR`
- `커버드콜`

`detection_source`는 다음처럼 더 세분화됩니다.

- `metadata`
- `name_heuristic`
- `name_heuristic_extended`
- `symbol_context`
- `unknown`

### 3. Common stock convergence

일반 주식(예: `000660`, `005930`)은 metadata가 부족해도,
가능한 경우 종목명 / 시장 문맥 / cached symbol metadata / remote symbol profile을 통해
`common_stock`으로 수렴하도록 보강했습니다.

다만 ETF/ETN-family 오탐 차단이 더 중요하므로,
판단 불가 상황이 완전히 사라지는 것은 아닙니다.

## Scanner observability fields

다음 필드를 additive하게 `scanner_output` / scanner artifact에 추가했습니다.

- `selected_asset_class_detected`
- `selected_asset_detection_source`
- `selected_asset_detection_field`
- `asset_detection_stats`
- `unknown_asset_candidate_count`
- `total_candidates_before_filter`
- `total_candidates_after_filter`

기존 필드도 유지됩니다.

- `excluded_candidate_count_by_asset_policy`
- `excluded_candidates_by_asset_policy`
- `asset_universe_policy`
- `asset_universe_policy_source`

또한 scanner event에도 분류 통계가 남아서,
run 하나만 봐도 unknown 비율과 exclusion 상황을 같이 볼 수 있습니다.

## Remaining gaps

- metadata / 종목명 / symbol context / remote profile 모두 부족하면 일부 `unknown`은 여전히 가능합니다.
- scanner는 이제 remote symbol lookup도 사용할 수 있어서 분류 품질은 좋아졌지만,
  candidate pool이 클 때는 lookup cost를 계속 관찰할 필요가 있습니다.
- 이번 작업은 entry/exit logic, strategist behavior, report structure는 건드리지 않았습니다.

## Next step after this work

다음 단계는 자산 분류가 아니라 entry quality입니다.
즉:
- `rebound_ok`
- `pullback_not_mature`
- `volume_confirmation_missing`

같은 monitor entry blocker를 따로 보는 것이 맞습니다.
