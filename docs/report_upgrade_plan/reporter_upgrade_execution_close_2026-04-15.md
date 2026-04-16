# Reporter Upgrade Execution Close
기준일: 2026-04-15

## 목표 대비 상태
- 상태: 진행 완료(운영 적용), 잔여 정리 항목만 남음
- 핵심 방향: `bundle` 중심 경로에서 `single_trade` 중심 경로로 기본 전환
- 원칙: additive only, 기존 report/trades 구조 유지

## 이번 턴 완료 항목
1. R1 read-model 구조화 고도화
- `libs/reporting/trade_read_model.py`
- `facts/provenance/context` 유지 + fact별 source 추적(`provenance.field_sources`) 강화
- context 확장:
  - `monitor_exit_trigger`
  - `thresholds_snapshot`
  - `watch_axes`
  - `same_day_reporter_status`
  - `data_source_quality`

2. R2 reporter agent 진입점 확장
- `libs/agent/reporter.py`
- `run_reporter_agent(trade_dir, policy)` 출력 계약:
  - `metadata`, `facts`, `provenance`, `context`, `narrative`, `status`
- read-model 불완전 시 degraded를 명시적으로 반환

3. R3 adapter 레이어 보강
- `libs/reporting/trade_report_ai.py`
- `build_separated_ai_trade_report()`가 reporter agent 경유
- 단, read-model 축약 fixture/구형 계약 입력일 때는 legacy `build_separated_report` fallback으로 호환 유지

4. R4 경로 단일화 시작(운영 기본값 전환)
- `graphs/nodes/reporter_node.py` 신설
- `graphs/commander_runtime.py` intraday report 호출을 reporter node로 통합
- 기본 모드: `single_trade`
- 명시 override:
  - `INTRADAY_REPORT_RUNTIME_MODE=bundle`

5. R0 Step4 회귀 체크 스크립트 추가
- `scripts/check_reporter_upgrade_regression.py`
- 지표:
  - closed trade report 존재/누락
  - all-fallback section 수
  - reporter fallback 수
  - canonical path 누락 수
  - thin trace 수
- 비교 모드:
  - `--day` 여러 개 입력 시 첫 day 대비 마지막 day delta 출력

## 테스트 결과
- `tests/test_trade_read_model.py` 통과
- `tests/test_reporter_agent_trade_entrypoint.py` 통과
- `tests/test_reporter_node.py` 통과
- `tests/test_check_reporter_upgrade_regression.py` 통과
- `tests/test_single_trade_report.py -k "commander_runtime_restores_intraday_bundle_helper_for_live_reports or readable_by_existing_reader"` 통과
- `tests/test_llm_model_policy.py -k "reporting_roles_use_applied_policy_models"` 통과

## 실데이터 회귀 체크(실행 결과)
실행:
```bash
python scripts/check_reporter_upgrade_regression.py --reports-root reports --day 2026-04-10 --day 2026-04-15 --json
```

요약:
- 2026-04-10: closed trade report 존재율 100%
- 2026-04-15: closed trade report 존재율 100%
- all-fallback section: 두 날짜 모두 0
- reporter fallback: 2026-04-15에서 1건 관측

## 운영 적용 상태
- intraday 기본 경로는 즉시 `single_trade`
- bundle 경로는 명시 override 시만 사용
- 기존 schema/경로 호환 유지

## 남은 정리 항목
1. `run_live_execution_bundle_report.py` 대형 코드의 core 분해(수동/복구용 wrapper 수준으로 축소)
2. `scripts/check_reporter_upgrade_regression.py` 지표 세분화(“canonical partial missing” vs “full missing” 분리)
3. 운영 close 포맷으로 일자별 체크 결과 누적 저장 자동화

