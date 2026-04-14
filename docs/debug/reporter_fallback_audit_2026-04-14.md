# reporter_fallback_audit_2026-04-14

## 현상 요약

재현 대상 trade `reports/trades/2026-04-14/TRD_20260414_000660_04` 기준으로 `ai_trade_report`의 section provenance가 거의 전부 `source="fallback"`, `confidence="low"`로 내려가 있다. 그런데 같은 trade artifact 안에는 실제 수치와 요약이 존재한다.

관찰된 모순은 다음과 같다.

- `ai_trade_report.json`의 `used_fallback_sections`는 빈 리스트인데, `section_provenance`는 거의 전부 `fallback`이다.
- `monitor_snapshot`에는 stop/take-profit 관련 숫자가 있는데, `monitor_stop_policy_trace`는 null/empty다.
- scanner 관련 섹션에는 selected score, runner-up 설명이 있는데, `selection_trace.ranked_candidates`는 빈 리스트다.
- `reporter_evaluation` / `errors_weaknesses_improvement_points`만 `reporter_analysis` 경로를 참조하지만, same-day linkage는 `missing`이다.

핵심 결론은 다음 두 가지다.

1. fallback 라벨은 주로 `section content fallback`이 아니라 `section provenance fallback`에서 발생한다.
2. canonical artifact가 아예 없는 것이 아니라, lifecycle bundle 단계에서 canonical path / evidence provenance / normalized trace가 부분적으로 유실되거나 empty placeholder에 막혀서 provenance가 fallback으로 강등된다.

## 재현 대상 artifact

주 재현 대상:

- `reports/trades/2026-04-14/TRD_20260414_000660_04/ai_trade_report.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/ai_trade_report.md`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/ai_trade_report_input.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/ai_trade_report_compact_input.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/lifecycle_bundle.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/_artifact_links.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/_provenance.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/entry.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/exit.json`

실제 canonical artifact 존재 확인:

- `reports/canonical/2026-04-14/18603da751d74a3bb502bbdc5a22aeb5/strategist.json`
- `reports/canonical/2026-04-14/18603da751d74a3bb502bbdc5a22aeb5/scanner.json`
- `reports/canonical/2026-04-14/0d19ddaa5bb744f89c04f59c07940792/monitor.json`
- `reports/canonical/2026-04-14/0d19ddaa5bb744f89c04f59c07940792/supervisor.json`
- `reports/canonical/2026-04-14/0d19ddaa5bb744f89c04f59c07940792/executor.json`

same-day reporter day file 부재 확인:

- `reports/dev/analysis/reporter_analysis/reporter_analysis_2026-04-14.json` 없음
- `reports/dev/analysis/reporter_analysis/reporter_analysis_2026-04-14.md` 없음

## 호출 경로

현재 trade report 생성 경로:

1. `graphs/commander_runtime.py`에서 intraday report helper 호출
2. `libs/reporting/intraday_trade_reports.py::generate_intraday_trade_artifacts(...)`
3. `scripts/run_live_execution_bundle_report.py`
4. run 단위 bundle 생성
5. lifecycle 단위 재조립
6. `libs/reporting/trade_story_pipeline.py::build_trade_story_input(...)`
7. `libs/reporting/trade_report_ai.py::generate_ai_trade_report(...)`

실제 provenance와 lifecycle 저장에 직접 관련된 함수:

- `scripts/run_live_execution_bundle_report.py::_prefer_canonical_payload` at `scripts/run_live_execution_bundle_report.py:2815`
- `scripts/run_live_execution_bundle_report.py::_build_same_day_reporter_linkage` at `scripts/run_live_execution_bundle_report.py:1938`
- lifecycle 재조립 at `scripts/run_live_execution_bundle_report.py:4066`
- lifecycle v1 저장 bridge at `scripts/run_live_execution_bundle_report.py:5402`
- provenance payload 생성 at `scripts/run_live_execution_bundle_report.py:5223`
- `libs/reporting/trade_story_pipeline.py::build_section_provenance` at `libs/reporting/trade_story_pipeline.py:721`
- `libs/reporting/trade_story_pipeline.py::build_trade_story_input` at `libs/reporting/trade_story_pipeline.py:2225`
- `libs/reporting/trade_story_pipeline.py::_build_scanner_selection_trace` at `libs/reporting/trade_story_pipeline.py:221`
- `libs/reporting/trade_story_pipeline.py::_build_monitor_stop_policy_trace` at `libs/reporting/trade_story_pipeline.py:290`
- `libs/reporting/trade_report_ai.py::_normalize_provenance_entry` at `libs/reporting/trade_report_ai.py:2155`
- `libs/reporting/trade_report_ai.py::_report_section_provenance` at `libs/reporting/trade_report_ai.py:2182`

## provenance 생성 경로

### 1. section provenance는 어디서 채워지는가

section provenance의 실제 생성은 두 단계다.

1. `libs/reporting/trade_story_pipeline.py::build_section_provenance` (`trade_story_pipeline.py:721`)
   - `bundle_out["evidence_provenance"]`에서 agent별 `source`를 읽는다.
   - `bundle_out["artifacts"]`에서 canonical path를 읽는다.
   - agent -> section mapping을 만든다.

2. `libs/reporting/trade_report_ai.py::_report_section_provenance` (`trade_report_ai.py:2182`)
   - `story_input["section_provenance"]`를 보고 report section별 provenance를 붙인다.
   - 여기서만 reporter 섹션이 `reporter_status_human` provenance를 참조한다.

### 2. report section -> provenance slot 매핑

`trade_report_ai.py:2186-2198` 기준:

- `executive_summary` -> `operator_conclusion_human`
- `market_context_at_entry` -> `market_context_human`
- `why_this_symbol_was_chosen` -> `scanner_reason_human`
- `entry_decision` -> `scanner_reason_human`
- `holding_monitoring_story` -> `monitor_reason_human`
- `exit_decision` -> `monitor_reason_human`
- `execution_quality` -> `execution_outcome_human`
- `scanner_filters` -> `filters_human`
- `guard_approval_result` -> `guard_reason_human`
- `reporter_evaluation` -> `reporter_status_human`
- `errors_weaknesses_improvement_points` -> `reporter_status_human`
- `full_timeline` -> `timeline`
- `final_operator_conclusion` -> `operator_conclusion_human`

따라서 `reporter_evaluation` / `errors_weaknesses_improvement_points`만 reporter 경로를 보는 것은 설계상 의도다. 나머지 섹션은 reporter analysis를 읽지 않는다.

## fallback 발생 조건

### 1. `source="fallback"` 으로 설정되는 정확한 조건

직접 원인은 `build_section_provenance` 내부 `_agent_source(agent)`이다.

`libs/reporting/trade_story_pipeline.py:728`

```python
return str(evidence_provenance.get(agent) or "fallback").strip().lower()
```

즉 다음 경우 무조건 `fallback`이 된다.

- `bundle_out["evidence_provenance"]`가 비어 있음
- 해당 agent key가 없음
- 해당 agent value가 empty string / falsy

중요한 점:

- canonical artifact 파일이 실제로 존재하는지와 별개다.
- provenance source는 `evidence_provenance`를 먼저 보고, path 존재 여부와는 독립적으로 fallback이 결정된다.

### 2. `confidence=low` / `completeness=0.35`가 되는 조건

`libs/reporting/trade_report_ai.py::_normalize_provenance_entry` (`trade_report_ai.py:2155-2178`)에서 다음과 같이 계산된다.

- `source == canonical` -> `confidence=high`, `completeness=1.0`
- `source in {direct_artifact, direct}` -> `confidence=medium`, `completeness=0.75`
- 나머지 -> `confidence=low`
- 그리고 `source == fallback`이면 `completeness=0.35`

따라서 provenance source가 fallback이면 각 section confidence는 자동으로 low가 된다.

### 3. `artifact_path=""` 가 비는 조건

`build_section_provenance`의 `_agent_path(agent)`는 다음 우선순위를 사용한다 (`trade_story_pipeline.py:730-737`).

1. `artifacts["canonical_<agent>_json"]`
2. reporter면 `artifacts["reporter_analysis_json"]`
3. 나머지는 `artifacts["agent_pipeline_trace_json"]`

문제는 lifecycle 재조립 단계에서 `artifacts`를 다시 만들 때 canonical path를 넣지 않는다는 점이다.

`scripts/run_live_execution_bundle_report.py:4110-4118`

여기서 lifecycle `artifacts`는 다음만 담는다.

- `agent_pipeline_trace_json`
- `agent_pipeline_trace_md`
- `trade_explain_json`
- `trade_explain_md`
- `reporter_analysis_json`
- `reporter_analysis_md`
- `operator_summary_json`
- `operator_summary_md`

즉 `canonical_commander_json`, `canonical_strategist_json`, `canonical_scanner_json`, `canonical_monitor_json`, `canonical_supervisor_json`, `canonical_executor_json`가 lifecycle `artifacts`에 복사되지 않는다. 그 결과:

- `lifecycle_bundle.json`의 canonical path가 빈 문자열로 저장된다.
- `_artifact_links.json`도 canonical path가 빈 문자열이다.
- `_provenance.json`의 `canonical_agent_artifact_paths`도 비어 보인다.

따라서 artifact가 실제로 없는 것이 아니라 lifecycle 저장 artifact가 canonical path를 잃어버린다.

## source hierarchy

### 현재 코드상 payload 선택 우선순위

`_prefer_canonical_payload` (`scripts/run_live_execution_bundle_report.py:2815`)의 실제 우선순위:

1. `normalized_trade_artifact`
2. `canonical`
3. `fallback_source` (직접 payload / event-derived fallback)

즉 run bundle 단계에서는 canonical을 실제로 우선 읽을 수 있다.

### 현재 provenance 표시 우선순위

최종 provenance 표시는 사실상 다음으로 축소된다.

1. lifecycle에 남아 있는 `evidence_provenance`
2. lifecycle `artifacts[canonical_*_json]`
3. 없으면 `fallback`

이때 lifecycle 쪽 `evidence_provenance`와 canonical path가 비어 있으면, run bundle 단계에서 canonical을 읽었더라도 section provenance는 전부 fallback이 된다.

### 기대 우선순위 제안

표시/해석 기준으로는 다음 순서가 더 적절하다.

1. canonical artifact
2. lifecycle bundle normalized data
3. event log / recovery evidence
4. synthesized fallback text

현재 문제는 실제 읽기 우선순위와 표시 provenance 우선순위가 분리되어 있다는 점이다.

## section별 실제 원인 표

| section | 현재 provenance slot | 실제 원인 | missing vs mismatch |
| --- | --- | --- | --- |
| `market_context_at_entry` | `market_context_human` | strategist canonical은 존재하지만 lifecycle `evidence_provenance`가 비어 fallback 강등 | contract / propagation mismatch |
| `why_this_symbol_was_chosen` | `scanner_reason_human` | canonical scanner는 존재, runner-up/score 설명도 존재. 하지만 empty `scanner_context` + `setdefault` 때문에 normalized trace 미반영 | contract mismatch |
| `entry_decision` | `scanner_reason_human` | 위와 동일 | contract mismatch |
| `holding_monitoring_story` | `monitor_reason_human` | holding events에는 실제 threshold가 있으나 top-level `monitor_stop_policy_trace`가 empty placeholder에 막힘 | contract mismatch |
| `exit_decision` | `monitor_reason_human` | 위와 동일 | contract mismatch |
| `execution_quality` | `execution_outcome_human` | execution details는 존재하지만 provenance source는 lifecycle `evidence_provenance.executor`에 의존 | propagation mismatch |
| `scanner_filters` | `filters_human` | scanner/supervisor payload는 존재하나 provenance source가 비어 fallback | propagation mismatch |
| `guard_approval_result` | `guard_reason_human` | supervisor artifact 존재, provenance source 비어 fallback | propagation mismatch |
| `reporter_evaluation` | `reporter_status_human` | reporter_analysis day file가 실제로 없음. 다만 lifecycle artifacts에는 예상 경로 문자열만 저장됨 | true missing + misleading path |
| `errors_weaknesses_improvement_points` | `reporter_status_human` | 위와 동일 | true missing + misleading path |
| `final_operator_conclusion` | `operator_conclusion_human` | operator summary text는 존재하지만 provenance source는 commander evidence_provenance에 의존 | propagation mismatch |
| `full_timeline` | `timeline` | timeline 내용은 존재하지만 provenance source slot은 별도 source를 안 받아 fallback 유지 | design limitation |

## 존재하지 않아서 fallback인지, 존재하지만 contract mismatch로 fallback인지

### 실제로 존재하지 않아서 fallback인 경우

- same-day `reporter_analysis_2026-04-14.json/.md`
- `same_day_reporter_linkage.status = missing`
- `same_day_reporter_linkage.reporter_analysis_day_file_found = false`

이 부분은 진짜 missing이다. reader가 못 읽는 것이 아니라 파일이 없다.

### 존재하지만 contract mismatch / propagation 문제로 fallback인 경우

- strategist/scanner/monitor/supervisor/executor canonical files
- scanner ranking rows
- monitor stop-loss / take-profit / trailing stop 수치
- execution quality 근거

이들은 실제로 canonical 또는 holding context에 존재하지만, lifecycle `evidence_provenance` / canonical path / normalized trace가 비어 있거나 empty placeholder에 막혀서 provenance fallback으로 보인다.

## 개별 질문별 확인 결과

### 1. ai_trade_report의 각 section provenance가 어디서 채워지는가

- `trade_story_pipeline.py:721` `build_section_provenance`
- `trade_report_ai.py:2182` `_report_section_provenance`
- `trade_report_ai.py:1028-1051`에서 report output에 적용

### 2. `source="fallback"` 정확한 조건

- `evidence_provenance[agent]`가 없거나 falsy이면 fallback (`trade_story_pipeline.py:728`)

### 3. `artifact_path=""`가 비는 이유

- lifecycle `artifacts`에 canonical path가 복사되지 않음 (`run_live_execution_bundle_report.py:4110-4118`)
- 그래서 `_agent_path()`가 빈 문자열을 반환 (`trade_story_pipeline.py:730-737`)

### 4. `reporter_evaluation` / `improvement_points`만 reporter_analysis 경로를 참조하는 이유

- `_report_section_provenance()` mapping 자체가 reporter slot을 이 두 섹션에만 연결 (`trade_report_ai.py:2195-2196`)

### 5. lifecycle_bundle / canonical artifacts가 실제로 존재해도 reporter가 못 읽는 구조인지

- 예. strategist/scanner/monitor/supervisor/executor는 canonical 파일이 존재한다.
- 하지만 lifecycle 저장 단계에서 canonical path와 provenance가 충분히 살아남지 않아서, report provenance는 그 존재를 반영하지 못한다.

### 6. 존재하지 않아서 fallback인지, 존재하지만 contract mismatch로 fallback인지

- reporter day file: true missing
- scanner/monitor/strategist/supervisor/executor provenance: mostly contract / propagation mismatch

### 7. `used_fallback_sections=[]`인데 `section_provenance`는 전부 fallback인 이유

`used_fallback_sections`는 `trade_report_ai.py:2906-2974`에서 내용 merge fallback만 센다.

```python
if not (isinstance(source_value, dict) and source_value):
    used_fallback_sections.append(section_key)
```

즉 이 값은 section content가 비었는지를 의미하고, provenance fallback과는 별개다. 현재 케이스는:

- content는 어느 정도 존재함 -> `used_fallback_sections=[]`
- provenance metadata는 비어 있음 -> `section_provenance[*].source=fallback`

### 8. `monitor_snapshot`에는 숫자가 있는데 `monitor_stop_policy_trace`는 null인 이유

- report output의 `monitor_snapshot` 기본 수치 필드는 `monitor_reason_human`에서 직접 채워진다.
- 하지만 nested `monitor_stop_policy_trace`는 `story_input.get("monitor_stop_policy_trace")`를 그대로 쓴다 (`trade_report_ai.py:2994-3001`, `3199`, `3206`).
- `build_trade_story_input()`는 canonical monitor에서 trace를 계산하지만 (`trade_story_pipeline.py:2376`, `2724`), 기존 empty placeholder가 있으면 `setdefault`가 덮어쓰지 않는다 (`trade_story_pipeline.py:2393`, `2741`).
- 결과적으로 숫자 필드는 있고, normalized trace는 null인 상태가 만들어진다.

### 9. scanner 점수/runner-up은 있는데 `selection_trace.ranked_candidates`가 빈 이유

- canonical scanner는 `candidate_ranking_table.rows`와 `ranked_candidates`를 가지고 있다 (`reports/canonical/2026-04-14/18603da751d74a3bb502bbdc5a22aeb5/scanner.json:884`).
- `build_trade_story_input()`는 `_build_scanner_selection_trace()`로 이를 복원한다 (`trade_story_pipeline.py:2354`, `2702`).
- 하지만 `scanner_reason_human.setdefault("scanner_selection_trace", ...)`와 `setdefault("ranked_candidates", ...)`가 empty placeholder를 덮어쓰지 못한다 (`trade_story_pipeline.py:2386-2389`, `2734-2737`).
- 그래서 summary/bullets는 실제 점수와 runner-up을 말하는데, normalized `selection_trace`는 빈 리스트로 남는다.

### 10. "근거 출처" 섹션이 operator/strategist 관점에서 왜 해석 불가능한가

현재 provenance는 다음만 보여 준다.

- `source`
- `artifact_path`
- `confidence`
- `completeness`

하지만 다음을 구분하지 못한다.

- canonical file이 실제 있었는데 lifecycle 저장 단계에서 path가 빠졌는지
- canonical data는 읽었는데 empty placeholder 때문에 normalized trace가 비었는지
- reporter analysis는 진짜로 파일이 없는지
- 같은 section 안에서 숫자는 실데이터인데 provenance label만 fallback인지

즉 operator/strategist 입장에서는 "왜 fallback인지"가 해석 불가능하다. 현재 라벨은 원인 설명력이 부족하다.

## 관련 함수 목록

- `libs/reporting/trade_story_pipeline.py::_build_scanner_selection_trace`
- `libs/reporting/trade_story_pipeline.py::_build_monitor_stop_policy_trace`
- `libs/reporting/trade_story_pipeline.py::build_section_provenance`
- `libs/reporting/trade_story_pipeline.py::build_trade_story_input`
- `libs/reporting/trade_story_pipeline.py::build_lifecycle_bundle`
- `libs/reporting/trade_report_ai.py::_normalize_provenance_entry`
- `libs/reporting/trade_report_ai.py::_report_section_provenance`
- `scripts/run_live_execution_bundle_report.py::_prefer_canonical_payload`
- `scripts/run_live_execution_bundle_report.py::_build_same_day_reporter_linkage`
- `libs/runtime/canonical_artifacts.py::load_run_canonical_artifacts`

## 관련 파일 목록

- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_report_ai.py`
- `scripts/run_live_execution_bundle_report.py`
- `libs/runtime/canonical_artifacts.py`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/ai_trade_report.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/ai_trade_report_input.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/lifecycle_bundle.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/_artifact_links.json`
- `reports/trades/2026-04-14/TRD_20260414_000660_04/_provenance.json`
- `reports/canonical/2026-04-14/18603da751d74a3bb502bbdc5a22aeb5/scanner.json`
- `reports/canonical/2026-04-14/0d19ddaa5bb744f89c04f59c07940792/monitor.json`

## 가장 먼저 고쳐야 할 3개 포인트

1. lifecycle 저장 시 canonical path 보존
   - `run_live_execution_bundle_report.py:4110-4118`의 lifecycle `artifacts`에 `canonical_*_json`을 그대로 복사

2. lifecycle에 `evidence_provenance` / `canonical_agent_artifacts` 전파 보존 확인
   - 초기 run bundle에서 채워진 값이 최종 `lifecycle_bundle.json`까지 유지되도록 propagation 점검

3. empty placeholder를 missing으로 취급하도록 normalize trace overwrite 조건 수정
   - `setdefault(...)` 대신 "empty dict/list/string이면 overwrite" 규칙 적용
   - 대상: `scanner_selection_trace`, `ranked_candidates`, `monitor_stop_policy_trace`, `monitor_blocker_trace`

## 수정 없이도 바로 개선 가능한 표시/문구 포인트

1. provenance 표시 문구 분리
   - `fallback`만 보여주지 말고 `fallback_due_to_missing_provenance`, `fallback_due_to_missing_reporter_day_file`처럼 이유를 별도 문자열로 표시

2. reporter path 문구 정직화
   - reporter day file이 실제 없으면 `artifact_path`에 예상 경로를 적는 대신 `expected_path`와 `found=false`를 분리해서 보여주기

3. section provenance tooltip/설명 추가
   - "content exists but provenance metadata missing" 여부를 라벨로 보여주면 operator가 현재 상태를 해석하기 쉬움

## 코드 수정이 필요한 포인트

1. lifecycle `artifacts`에 canonical path 누락 수정
2. lifecycle persisted bundle에서 `evidence_provenance` / `canonical_agent_artifacts`가 비지 않게 propagation 보강
3. `build_trade_story_input()`의 `setdefault` 기반 normalize trace 주입을 empty placeholder aware overwrite로 변경
4. reporter artifact path 저장 시 실제 file exists 여부와 expected path를 분리

## 리스크 없는 최소 패치 제안

대규모 리팩토링 없이 바로 갈 수 있는 최소 수정안은 아래 3개 이하다.

1. lifecycle `artifacts`에 `canonical_*_json` 복사
   - low risk
   - 기존 contract 유지
   - provenance `artifact_path` 즉시 개선 가능

2. `build_trade_story_input()`에서 `scanner_selection_trace` / `ranked_candidates` / `monitor_stop_policy_trace`에 대해 empty placeholder overwrite 허용
   - low risk
   - summary text는 그대로 두고 normalized trace만 채움

3. `reporter_analysis_json`를 항상 경로 문자열로 넣지 말고, 실제 존재하지 않으면 빈 문자열 + `same_day_reporter_linkage.expected_path` 별도 표시
   - low risk
   - misleading provenance 감소

## 조사 결론

현재 ai_trade_report provenance 전면 fallback은 "reporter가 아무 것도 못 읽었다"가 아니라 다음이 겹친 결과다.

- lifecycle bundle 단계에서 canonical path / evidence provenance가 충분히 유지되지 않음
- story normalization이 empty placeholder를 덮어쓰지 못함
- reporter same-day linkage는 실제로는 missing인데, artifacts에는 예상 경로가 남아 해석을 더 어렵게 만듦

즉 root cause는 크게 두 축이다.

1. provenance propagation loss
2. empty placeholder precedence bug

반면 reporter day file 부재는 실제 missing이다. 따라서 reporter 섹션만큼은 contract mismatch가 아니라 genuine missing으로 분류하는 것이 맞다.
