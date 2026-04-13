# Entry Blocker Family Breakdown Close (2026-04-11)

## Why this analysis step exists
- `pullback_timing` 같은 family만 보면 blocker가 크게 보이지만, 실제 튜닝 대상은 그 안의 raw blocker일 수 있다.
- 예를 들어 `pullback_timing` 안에는
  - `pullback_not_mature`
  - `pullback_mature`
  - `pullback_volume_path_ok`
  - `pullback_structure_ok`
  가 함께 섞일 수 있다.
- 따라서 family만 보고 threshold를 완화하면, 실제 병목과 다른 축을 건드릴 위험이 있다.

## What was added
- `entry_blocker_read_model`에 다음 분석 필드를 추가했다.
  - `blocker_family_raw_breakdown`
  - `blocker_family_explanations`
  - `raw_blocker_explanations`
  - `scanner_quality_suspected`
  - `scanner_quality_reason`
  - `scanner_quality_reason_explanation`
- 집계 범위:
  - top-level summary
  - `by_symbol.*`
  - `by_time_bucket.*`
  - `by_final_decision.*`

## Family to raw blocker interpretation
- 이제 `pullback_timing` family를 보면 내부 raw blocker 기여도를 바로 읽을 수 있다.
- 예시:
  - `pullback_not_mature`: 눌림이 아직 성숙하지 않음
  - `pullback_mature`: 눌림 성숙 확인 단계
  - `pullback_volume_path_ok`: 눌림 경로는 허용 범위이나 추가 확인 필요
  - `pullback_structure_ok`: 눌림 구조는 유지 중

## Scanner quality suspected flag
- 이 flag는 runtime decision에 연결되지 않는 analysis-only signal이다.
- 현재는 아래 조건을 약하게 표시한다.
  - `too_extended_from_vwap` 존재
  - `volume_confirmation_missing`와 낮은 scanner score 동시 발생
  - selected candidate confidence가 낮음
- 해석 주의:
  - 이 flag는 “scanner가 문제일 가능성”을 약하게 표시할 뿐이다.
  - monitor gate issue와 구분하는 보조 신호로만 사용해야 한다.

## How to use
- 날짜 전체:
  - `venv\Scripts\python.exe scripts\analyze_entry_blockers.py --date YYYY-MM-DD`
- family 집중:
  - `venv\Scripts\python.exe scripts\analyze_entry_blockers.py --date YYYY-MM-DD --family pullback_timing`
- symbol + family drilldown:
  - `venv\Scripts\python.exe scripts\analyze_entry_blockers.py --date YYYY-MM-DD --family pullback_timing --symbol 000660 --limit 20`

## Scope boundary
- 이 단계는 여전히 분석 단계다.
- 이번 작업에서는 아래를 바꾸지 않았다.
  - runtime threshold
  - monitor gate semantics
  - scanner ranking
  - strategist policy
  - exit policy

## Next tuning direction
- 다음 단계에서는 family가 아니라 raw blocker 기준으로 우선순위를 정하는 것이 맞다.
- 현재 우선 후보 예시:
  - `pullback_not_mature`
  - `below_vwap_reclaim_not_ready`
  - `breakout_not_ready`
  - `volume_confirmation_missing`
