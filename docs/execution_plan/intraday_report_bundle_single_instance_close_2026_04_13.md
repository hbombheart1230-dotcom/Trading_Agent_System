# Intraday Report Bundle Single-Instance Close (2026-04-13)

## Why this patch was needed
완료된 `ai_trade_report` 파일 수 자체는 trade당 대체로 1개였지만, 실제 운영 문제는 `run_live_execution_bundle_report.py` child가 여러 체인으로 동시에 살아 있으면서 같은 범위를 반복 스캔하는 구조였다. 이 때문에:
- python/cmd 창이 중복으로 보였고
- 동일한 역할의 report bundle app이 여러 개 떠 있는 것처럼 보였고
- `--max-runs 200` 기반 광범위 재스캔으로 비용/지연 체감이 커졌다.

## Root cause
1. parent helper가 bundle child spawn 전에 lock만 부분적으로 확인했다.
2. lock이 없는데 child process가 살아 있는 경우를 완전히 막지 못했다.
3. child script는 live 경로에서도 day-wide execution sweep 성격을 유지했다.
4. `ai_trade_report`는 동일 입력이라도 fingerprint/idempotency 없이 다시 생성 가능했다.

## What now guarantees single-instance
single-instance는 아래 3중 구조로 보장한다.
- parent pre-spawn dedupe:
  - lock payload 확인
  - active child process scan 확인
  - 둘 중 하나라도 active면 spawn skip
- child self-guard:
  - 시작 시 lock + process scan 재확인
  - 같은 role(`intraday_trade_report_bundle`) active owner가 있으면 즉시 skip
- lock lifecycle:
  - `reports/runtime/intraday_trade_report_bundle.lock`
  - `pid`, `parent_pid`, `role`, `created_at`, `started_at`, `touched_at`, `heartbeat`, `target_run_id`, `target_symbol` 기록
  - stale lock + dead pid면 제거 후 진행

## Per-trade targeted generation
live 경로 기본 bundle argv는 더 이상 `--max-runs 200` sweep를 사용하지 않는다.
대신 targeted mode를 사용한다.
- `--target-run-id <run_id>`
- `--target-symbol <symbol>`
- `--role intraday_trade_report_bundle`

child script는 targeted mode일 때:
- run bundle 생성은 `target_run_id` 1건만 처리한다.
- lifecycle 재구성에 필요한 prior same-symbol run은 `lifecycle_context_run_ids`로만 읽는다.
- 따라서 현재 trade lifecycle을 설명하는 데 필요한 최소 context만 유지하고, target run과 무관한 run bundle 재생성은 피한다.

즉 live 기본 경로는 이제 "현재 trade/run 중심"으로 움직인다.

추가 보강:
- `generate_on_open=false`이면 BUY 시점에는 parent가 bundle child를 아예 띄우지 않는다.
- 즉 live 기본 경로는 SELL/closure 중심으로만 full trade report를 생성하고, open lifecycle은 pending으로 남긴다.

## Fingerprint / idempotency
`reports/trades/<day>/<trade_id>/reports/report_generation_state.json`를 추가한다.

현재 최소 관리 대상:
- `ai_trade_report`
- `operator_brief` (state/provenance 수준)

`ai_trade_report` fingerprint는 아래 입력으로 계산한다.
- `trade_id`
- `run_id`
- `component`
- `lifecycle_status`
- `story_type`
- `model`
- `trade_story_input` content hash
- compact input content hash

동일 fingerprint + 기존 성공 artifact가 있으면:
- LLM 재호출 skip
- `report_generation_skipped_fingerprint_match` event 기록
- 기존 artifact 재사용

## New observability
이벤트 예시:
- `report_bundle_spawn_requested`
- `report_bundle_spawn_skipped_existing_process`
- `report_bundle_lock_acquired`
- `report_bundle_lock_released`
- `report_bundle_stale_lock_removed`
- `report_bundle_stale_process_terminated`
- `report_generation_skipped_fingerprint_match`

최소 payload:
- `pid`
- `parent_pid`
- `role`
- `lock_path`
- `reason`
- `trade_id`
- `run_id`
- `component`

## Operator checklist
운영자는 아래를 보면 된다.
1. 동일 시점에 `run_live_execution_bundle_report.py` python process가 1개 이하인지
2. `reports/runtime/intraday_trade_report_bundle.lock`에 `pid`/`heartbeat`가 들어오는지
3. 동일 trade에서 `ai_trade_report_llm_response.json`가 중복 생성되지 않는지
4. skip 이벤트가 `events.jsonl`에 남는지
5. live argv에 더 이상 `--max-runs 200`가 기본으로 붙지 않는지

## Remaining gaps
- live bundle은 안정화됐지만, operator brief 자체는 on-demand/UI 경로라 별도 role의 runtime dedupe는 후속으로 넓힐 수 있다.
- targeted mode는 이제 target run + lifecycle context 중심까지 줄였지만, day-level auxiliary analysis(`trade_explain`, `reporter_analysis`)를 더 가볍게 쓰는 여지는 남아 있다.
- lock이 없는데 child만 오래 살아 있는 orphan 케이스는 stale process termination으로 회수하도록 보강했지만, 운영에서는 `stale_process_terminated` 이벤트가 반복되는지 계속 보는 편이 좋다.
