# Lifecycle Linkage Close (2026-04-16)

## Root Cause (One Line)
`_build_trade_lifecycles` SELL 처리에서 `active_by_symbol[symbol]`가 비어 있으면 기존 day open lifecycle 재사용 없이 즉시 새 partial trade를 생성해 same-symbol SELL-only split가 발생했다.

## Exact Pre-Fix Split Condition
기존 분기 조건은 아래와 같았다.

- 함수: `scripts/run_live_execution_bundle_report.py::_build_trade_lifecycles`
- 조건:
  - `action == "SELL"`
  - `active_by_symbol.get(symbol)`가 `None`
- 결과:
  - `_next_trade_id(symbol)`로 새 trade 생성
  - `status = "partial"`
  - entry 없이 SELL-only lifecycle 생성

즉 split은 `targeted_context` 자체가 아니라, SELL 시점에 메모리 active lifecycle이 없을 때 attach fallback이 없었던 것이 직접 원인이었다.

## Modified Files
- `scripts/run_live_execution_bundle_report.py`
- `tests/test_live_execution_bundle_report_runtime_recovery.py`

## Added `lifecycle_attach_debug`
아래 필드를 lifecycle 단위 debug로 추가했다.

- `matched_open_trade_id`
- `candidate_open_trade_ids`
- `attach_match_reason`
- `new_trade_created_reason`
- `recovered_lifecycle_reason`
- `execution_symbol`
- `execution_ts`
- `execution_side`
- `execution_order_id`
- `execution_run_id`
- `execution_filled_qty`
- `execution_filled_price`

저장 위치:
- lifecycle 내부: `lifecycle["lifecycle_attach_debug"]`
- bundle top-level: `lifecycle_bundle["lifecycle_attach_debug"]`
- compatibility flat payload: `lifecycle_bundle_v1["lifecycle_attach_debug"]`

## Added Tests
- `test_build_trade_lifecycles_attaches_sell_to_existing_open_candidate_when_buy_snapshot_missing`
- `test_build_trade_lifecycles_creates_partial_only_when_no_attach_candidate_exists`
- `test_build_trade_lifecycles_prefers_current_active_open_over_existing_candidate`

## Test Results
- `pytest tests/test_live_execution_bundle_report_runtime_recovery.py tests/test_check_trade_report_runtime_regression.py -q` -> `9 passed`
- `pytest tests/test_run_ai_trade_report_batch.py tests/test_trade_story_pipeline_enrichment.py -q` -> `26 passed`
- `python scripts/check_trade_report_runtime_regression.py` -> `cases=3 failed=0`

## Recovered Trades (Confirmed)
기존 broken 분류에 있던 trade 중 복구 확인된 케이스:

- `TRD_20260416_000660_02`
- `TRD_20260416_000660_03`
- `TRD_20260416_000660_04`
- `TRD_20260416_000660_05`
- `TRD_20260416_000660_06`
- `TRD_20260416_005930_01`
- `TRD_20260416_005930_02`
- `TRD_20260416_005930_03`

기존 healthy 유지 확인:
- `TRD_20260416_000660_01`
- `TRD_20260416_047040_01`

## 2026-04-16 Thin Case Check
`2026-04-16` 기준 thin lifecycle 케이스는 `0건` 확인.

## Remaining Issue (Out of Lifecycle Scope)
남은 이슈는 lifecycle linkage가 아니라 execution snapshot observability 품질이다.

주요 잔여 항목:
- `order_id` 빈약
- `filled_price` 빈약
- 일부 run에서 execution payload가 `status/ord_no/price`를 충분히 싣지 못함

다음 슬라이스는 lifecycle 로직을 추가 변경하지 않고, execution snapshot source/merge/fallback 경로를 별도로 보강한다.
