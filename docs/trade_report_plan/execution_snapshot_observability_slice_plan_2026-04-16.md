# Execution Snapshot Observability Slice Plan (2026-04-16)

## Goal
lifecycle attach는 고정된 상태를 유지하고, `order_id`/`filled_price` 등 execution snapshot 필드의 공백 원인을 source/merge/fallback 경로에서 분리 진단한다.

## Non-Goals
- lifecycle attach/merge 조건 변경
- report layer 문장/LLM 품질 튜닝
- trade artifact schema breaking

## Scope
대상 파일:
- `scripts/run_live_execution_bundle_report.py`

핵심 경로:
- `_normalize_execution_payload`
- `_build_run_snapshots`
- `_build_execution_details_from_bundle`
- entry/exit `execution_details` write 경로

## Diagnostic Checklist
1. source 분리
- event payload source (`execute_from_packet.execution`)
- executor canonical source
- context backfill source (`monitor_context`, `execution_context`)

2. merge 우선순위 확인
- `order_id` 최종 선택 우선순위
- `avg_price/filled_price` 최종 선택 우선순위
- `qty/status` 우선순위

3. fallback 유효성
- regex 기반 order_id 추출 성공/실패 케이스
- `price` fallback이 `avg_price/current_price`로 과도하게 대체되는지

## Minimal Additive Outputs (if needed)
- `execution_snapshot_debug` 필드 추가 (분석용)
  - `order_id_source`
  - `filled_price_source`
  - `status_source`
  - `qty_source`
  - `missing_fields`

## Acceptance Criteria
- lifecycle field는 현 상태 유지
- `order_id`/`filled_price` 공백 케이스에서 "왜 비었는지"를 artifact만으로 설명 가능
- healthy case(`000660_01`, `047040_01`) 회귀 없음

## Initial Candidate Cases
- `TRD_20260416_000660_03`
- `TRD_20260416_000660_05`
- `TRD_20260416_005930_02`
(attach는 정상, execution snapshot 품질만 점검)
