# Reporter Pre-Recovery Stabilization Plan
기준일: 2026-04-15

## 결론
`docs/report_upgrade_plan/reporter_agentification_execution_plan_2026-04-15.md`는 유지한다. 다만 바로 그 계획으로 들어가면 비효율이 크다.

우선순위는 다음 순서가 맞다.

1. report provenance / linkage / lifecycle propagation 회귀 복구
2. intraday report 안정성 재검증
3. 그 다음 reporter upgrade plan 실행

이유는 단순하다.
현재 문제는 “기능이 아예 없다”가 아니라, `2026-04-10` 기준 정상적으로 보이던 provenance가 `2026-04-13`~`2026-04-14` 패치로 흔들린 상태다. 이 상태에서 reporter agentification을 먼저 진행하면, broken input 위에 새 구조를 얹게 되어 중복 작업이 발생한다.

## 왜 업그레이드보다 복구가 먼저인가
현재 확인된 상태는 아래와 같다.

- closed trade report generation 자체는 회귀가 대부분 막혔다.
- 그러나 provenance 품질은 `2026-04-10` 대비 `2026-04-13`, `2026-04-14`에서 악화됐다.
- 핵심 붕괴 지점은 다음 세 가지다.
  - lifecycle 단계에서 `evidence_provenance`가 비는 경우가 생김
  - lifecycle artifacts에 canonical path가 충분히 보존되지 않음
  - `build_trade_story_input()`에서 empty placeholder가 normalized trace를 막아 scanner / monitor trace가 비어 보임

즉 지금은 reporter를 고도화할 단계가 아니라, reporter가 읽는 입력을 다시 신뢰 가능한 상태로 되돌리는 단계다.

## 이 문서의 역할
이 문서는 `reporter_agentification_execution_plan_2026-04-15.md`의 선행 조건을 정의한다.

정리하면:
- 본 문서 = R0 안정화 / 사전 복구 플랜
- 기존 문서 = R1 이후 구조 개선 / agentification 플랜

## R0 범위
이번 선행 복구 플랜의 범위는 아래로 제한한다.

1. provenance propagation 복구
2. canonical artifact path 보존
3. same-day reporter linkage 정직화
4. scanner / monitor normalized trace 복구
5. closed trade report 생성 안정성 재검증

다음은 R0 범위 밖이다.

- reporter architecture 재설계
- prompt 개편
- 새로운 agent 역할 분리
- report schema 재설계
- UI 변경
- 전략/매매 로직 변경

## 현재 기준 회귀 포인트
### 1. provenance 회귀
`2026-04-10` report input에서는 canonical / direct_artifact provenance가 유지된다.
반면 `2026-04-13`, `2026-04-14`에는 section provenance가 전부 `fallback / low`로 내려가는 사례가 확인됐다.

대표 비교 대상:
- baseline: `reports/trades/2026-04-10/TRD_20260410_047040_04/ai_trade_report_input.json`
- degraded: `reports/trades/2026-04-14/TRD_20260414_000660_04/ai_trade_report_input.json`

### 2. lifecycle propagation 회귀
실제 canonical artifact가 존재해도 lifecycle 재조립 이후 아래가 비는 경우가 있었다.

- `evidence_provenance`
- `artifacts.canonical_*_json`
- `scanner_selection_trace.ranked_candidates`
- `monitor_stop_policy_trace`

### 3. reporter linkage 혼선
same-day reporter file이 실제로 없을 때도 expected path와 actual artifact path가 뒤섞여 보여 해석이 어려웠다.

## R0 목표 상태
R0 종료 기준은 아래다.

1. `section_provenance`가 더 이상 전부 `fallback`으로 무너지는 closed trade가 없어야 한다.
2. `evidence_provenance`가 lifecycle bundle에 비지 않고 남아야 한다.
3. `canonical_*_json` path가 lifecycle 저장물에 유지돼야 한다.
4. `scanner_selection_trace`와 `monitor_stop_policy_trace`가 empty placeholder 때문에 비지 않아야 한다.
5. same-day reporter analysis가 없으면 `missing`이 정직하게 드러나야 한다.
6. closed trade는 report existence와 provenance 품질이 동시에 확인 가능해야 한다.

## 실행 순서
### Step 1. Provenance 복구
우선 아래 propagation을 복구한다.

- lifecycle artifacts canonical path 보존
- `evidence_provenance` lifecycle 전파
- same-day linkage honest missing 상태 유지

### Step 2. Normalized trace 복구
`build_trade_story_input()`에서 아래 필드가 placeholder면 normalized trace로 덮어쓸 수 있게 유지한다.

- `scanner_selection_trace`
- `ranked_candidates`
- `monitor_stop_policy_trace`
- `monitor_blocker_trace`

### Step 3. Single-path / bundle-path 공통 진단 보장
single helper를 쓰든 bundle을 쓰든 최소한 아래는 동일해야 한다.

- canonical artifact path
- evidence provenance
- same-day reporter linkage
- scanner / monitor normalized trace

### Step 4. Regression check 고정
날짜별로 최소 비교 지표를 고정한다.

- closed trade count
- ai report existence count
- all-fallback section count
- reporter fallback count
- missing canonical path count
- thin trace count

## 업그레이드 플랜으로 넘어가는 조건
아래 조건을 충족하기 전에는 `reporter_agentification_execution_plan_2026-04-15.md`의 R1 이상으로 들어가지 않는다.

1. `2026-04-10` 대비 provenance 품질이 유사 수준으로 회복
2. `2026-04-13`, `2026-04-14` 회귀 원인이 정리되고 재발 방지 확인
3. closed trade report 생성 안정성 유지
4. same-day linkage missing/linked 상태가 해석 가능
5. scanner/monitor trace 공란 현상이 구조적으로 제거

## 중복 작업을 피하기 위한 원칙
1. R0에서는 입력 propagation만 고친다.
2. R1 이후에만 reporter 구조 분리를 진행한다.
3. R0에서 만든 보강 필드는 R1 read-model의 입력으로 재사용한다.
4. provenance 문제를 prompt나 wording으로 가리지 않는다.

## 가장 먼저 볼 파일
- `scripts/run_live_execution_bundle_report.py`
- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_report_ai.py`
- 필요 시 `libs/reporting/single_trade_report.py`

## 현재 판단
지금은 기존 `report_upgrade_plan`과 같이 가는 단계가 아니다.

정확한 순서는:
- 먼저 `사전 복구 플랜(R0)` 수행
- 그 결과를 검증
- 그 다음 기존 `reporter_agentification_execution_plan_2026-04-15.md`로 진입

이 순서가 가장 덜 중복되고, 회귀 원인을 가장 적게 다시 밟는다.
