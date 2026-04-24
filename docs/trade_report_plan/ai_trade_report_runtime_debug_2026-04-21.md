# AI Trade Report Runtime Debug

## Scope

2026-04-21 장중 `ai_trade_report` / reporter LLM 호출 관측 문제를 정리한다.

사용자 관측:

- OpenRouter 대시보드에서 `ai_trade_report` 계열 호출이 `14:21 KST` 이후 보이지 않음
- 저장된 report에 `최종 생애주기 결론은 기록되지 않았습니다.`가 남음

## Confirmed Facts

1. `14:21 KST` 이후에도 report bundle subprocess는 계속 떴다.

이벤트 로그:

- `data/logs/events.jsonl`
- 예:
  - `2026-04-21T14:20:00+09:00` `report_bundle_spawn_requested`
  - `2026-04-21T14:20:02+09:00` `report_bundle_spawned_background`
  - `2026-04-21T14:22:02+09:00` `report_bundle_lock_released`

즉 report bundle 자체가 멈춘 건 아니다.

2. spawned command에는 `--trade-report-ai`가 붙어 있었다.

이벤트 payload 기준:

- `...\\scripts\\run_live_execution_bundle_report.py ... --trade-report-ai --json --target-run-id ...`

즉 policy gate에서 `trade_report_ai`가 완전히 꺼진 상태도 아니다.

3. 현재 저장된 `ai_trade_report.json` / `ai_trade_report_llm_response.json`는 live 결과를 그대로 보여주지 않는다.

이유:

- 장후 `scripts/run_ai_trade_report_batch.py --local-debug` 재생성이 실행됨
- 그 결과 현재 저장본에는:
  - `generation.mode = local_debug`
  - `reason = local_debug_no_llm`
  - `llm_response_artifact.status = fallback`
  가 들어 있다

즉 현재 저장본만 보고 live 시점 LLM 호출 유무를 단정하면 안 된다.

## Observability Gap

현재 관측 공백:

1. live report bundle는 spawn / lock / completion 이벤트만 충분히 남고,
2. `ai_trade_report` generation attempt/result 이벤트는 남기지 않는다.

그래서 아래를 즉시 판별하기 어렵다.

- OpenRouter 호출 시도 여부
- fallback reason
- LLM error 여부
- fingerprint reuse 여부

## Confirmed Runtime Bug

background report bundle subprocess가 script wrapper가 아니라 module file을 직접 띄우고 있었다.

문제 코드:

- `libs/reporting/live_execution_bundle_runner.py`

영향:

- subprocess 기준 repo root 해석이 `C:\\Trading_Agent_System\\libs`로 흔들릴 수 있음
- 실제 이벤트에서도 lock path가 두 종류로 섞였다
  - expected: `C:\\Trading_Agent_System\\reports\\runtime\\intraday_trade_report_bundle.lock`
  - wrong: `C:\\Trading_Agent_System\\libs\\reports\\runtime\\intraday_trade_report_bundle.lock`

이건 runtime stability bug다.

## Required Fixes

1. report bundle subprocess는 wrapper script를 통해서만 실행
2. report bundle runtime path는 repo root 기준으로 통일
3. `ai_trade_report` generation attempt/result 이벤트 기록
4. local-debug regeneration이 live LLM artifact를 덮기 전에 이전 artifact 백업

## Interpretation

현재 시점에서 확정할 수 있는 말:

- `14:21 KST` 이후 report bundle는 계속 실행됐다
- `--trade-report-ai`도 붙어 있었다
- 하지만 current stored artifact는 post-market local-debug regeneration으로 덮였기 때문에,
  live 시점 OpenRouter 호출 여부를 현재 저장본만으로 증명할 수는 없다

그래서 이 문제의 1차 답은:

- `report bundle stopped`: 아님
- `observability is sufficient`: 아님
- `runtime path/lock handling has a bug`: 맞음

## Follow-up

- eporter_evaluation now has a same-day fallback path based on closed same-day trade reports when linked reporter artifacts are absent.
- The remaining work on this track is live operational verification, not additional report-builder structure.
