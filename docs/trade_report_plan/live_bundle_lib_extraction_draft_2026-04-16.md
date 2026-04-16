# Live Bundle Lib Extraction Draft (Responsibilities Only)

## Module Candidate 1: `libs/reporting/trade_lifecycle_builder.py`
책임:
- run snapshots -> lifecycle assemble
- BUY/SELL/holding attach rules
- same-symbol attach fallback
- lifecycle recovery metadata (`trade_origin`, `lifecycle_completeness`)
- lifecycle attach debug payload 생성

노출 함수 초안:
- `build_trade_lifecycles(day, run_snapshots, run_bundles, existing_open_lifecycles_by_symbol=None)`
- `load_existing_open_lifecycle_candidates(reports_root, day)`
- `derive_trade_recovery_metadata(lifecycle, evidence_completeness, section_provenance)`

## Module Candidate 2: `libs/reporting/trade_execution_snapshot.py`
책임:
- execution payload normalize
- run-level execution snapshot 구성
- execution detail source merge/fallback
- order/filled/qty/status source provenance

노출 함수 초안:
- `normalize_execution_payload(payload)`
- `build_run_snapshots(...)`
- `build_execution_details_from_bundle(bundle, context)`
- `build_execution_snapshot_debug(...)`

## Module Candidate 3: `libs/reporting/trade_bundle_state.py`
책임:
- trade bundle persistence orchestration
- trade artifact paths / write order
- generation state + diagnostics state sync
- per-trade idempotent overwrite 전략

노출 함수 초안:
- `persist_trade_bundle_outputs(...)`
- `sync_report_generation_state(...)`
- `sync_trade_health_and_links(...)`

## Extraction Order (Low-Risk)
1. `trade_execution_snapshot.py` 먼저 추출 (pure helper 비중 높음)
2. `trade_lifecycle_builder.py` 추출 (attach 로직 단위 테스트 유지)
3. `trade_bundle_state.py` 추출 (I/O orchestration 최종 정리)

## Invariants During Extraction
- `report/trades/*` 구조 불변
- lifecycle linkage behavior 불변
- regression harness(`check_trade_report_runtime_regression.py`) green 유지
