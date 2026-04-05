# Phase 5-4 Codex Task Breakdown
**대상 저장 경로:** `docs/execution_plan/phase_5_4_codex_tasks.md`  
**함께 볼 문서:** `docs/execution_plan/phase_5_4_execution_plan.md`  
**주 독자:** Codex  
**문서 목적:** 상위 실행 계획 문서를 실제 수정 작업 단위로 분해하여, Codex가 바로 코드 변경을 시작할 수 있게 한다.

---

# 0. 작업 시작 전 절대 규칙

## 0.1 절대 깨면 안 되는 것
1. `reports/trades/*` 저장 구조 변경 금지
2. 기존 canonical artifact 경로/핵심 의미 변경 금지
3. 기존 필수 DTO required field 삭제 금지
4. additive 변경 우선
5. Commander LLM 도입 금지
6. Read-model에 LLM 사용 금지
7. Report facts를 LLM에 맡기지 말 것

## 0.2 작업 철학
- 이번 단계는 **대공사**가 아니라 **ownership/wiring 정리**
- 기존 시스템을 버리지 말고, owner / consumer / provenance를 명확히 하는 방향으로 간다
- downstream breakage를 피하기 위해 mirrored field는 당분간 유지할 수 있다
- 문서와 테스트를 함께 갱신한다

## 0.3 작업 순서 원칙
아래 순서를 지킨다.

```text
Task 1 Commander
→ Task 2 Strategist
→ Task 3 Scanner
→ Task 4 Monitor
→ Task 5 trade_read_model
→ Task 6 daily_summary_read_model
→ Task 7 symbol_read_model
→ Task 8 report fact/narrative boundary docs
```

Commander ownership이 정리되기 전에는 read-model full 설계를 먼저 굳히지 말 것.

---

# 1. Task 1 — Commander ownership 강화

## 1.1 목적
Commander를 파이프라인 시작점이 아니라, **route / invocation / applied policy owner**로 명확히 만든다.

## 1.2 우선 대상 파일
- `graphs/commander_runtime.py`
- `graphs/nodes/commander_node.py` (존재 시)
- `libs/contracts/agent_outputs.py`
- commander canonical artifact writer 관련 파일

## 1.3 해야 할 일
1. `commander_decision` 필드 표준화
   - `market_operating_posture`
   - `strategist_invocation`
   - `strategist_refresh_requested`
   - `strategist_refresh_reason`
   - `allowed_playbooks`
   - `banned_playbooks`
   - `scanner_mission`
   - `monitor_mission`
   - `no_trade_reason_code`
   - `decision_summary`
   - `route_path`
   - `applied_policy_source`
   - `applied_policy_source_chain`

2. route/path를 명확한 enum/문자열 surface로 고정
   예:
   - `full_cycle`
   - `cached_strategist`
   - `scanner_then_monitor`
   - `monitor_only`
   - `no_trade_path`

3. strategist invocation reason을 명시적으로 남기기
   예:
   - `fresh_start`
   - `cache_stale`
   - `scanner_quality_low`
   - `monitor_blocker_repeat`
   - `manual_refresh`
   - `not_required`

4. commander applied policy provenance를 더 명확히 기록
   - proposal source
   - selected source
   - fallback 여부
   - source chain

5. commander canonical artifact에 owner 관점 필드가 충분히 보이게 하기

## 1.4 하지 말 것
- strategist output을 직접 계산하는 로직을 commander에 넣지 말 것
- monitor 수치 정책 생성 로직을 commander에 넣지 말 것
- LLM 호출 추가 금지

## 1.5 수용 기준
- `commander.json`만 보고 이번 run의 route와 strategist invocation 이유를 이해할 수 있어야 한다
- applied policy provenance가 한 번에 보인다
- strategist를 skip하는 path가 코드/아티팩트 상 명시된다

## 1.6 테스트/검증
- commander artifact snapshot test
- route/path enum test
- strategist invocation reason propagation test

---

# 2. Task 2 — Strategist를 proposal owner로 정리

## 2.1 목적
Strategist를 final owner처럼 보이지 않게 하고, **proposal package producer**로 명확히 만든다.

## 2.2 우선 대상 파일
- `graphs/nodes/strategist_node.py`
- `libs/strategies/contracts.py`
- `libs/contracts/agent_outputs.py`

## 2.3 해야 할 일
1. strategist_output 필드를 세 범주로 구분
   - proposal fields
   - mirrored commander fields
   - diagnostic/runtime metadata

2. 아래 항목은 final owner가 commander임을 metadata 또는 문서상 명확히 반영
   - playbook final allowance
   - no-trade posture
   - applied policy
   - strategist invocation / refresh

3. strategist output 안의 commander mirrored field는 유지 가능
   단, owner metadata를 분리해서 혼동 줄이기

4. policy proposal surface를 명확히 유지
   - `themes`
   - `avoid_themes`
   - `playbook`
   - `scanner_bias`
   - `scanner_priority`
   - `monitor_entry_policy`
   - `monitor_policy`
   - `exit_policy`
   - `policy_rationale`

5. LLM status / repair / blocked metadata는 유지

## 2.4 하지 말 것
- proposal field를 지금 당장 대거 삭제하지 말 것
- downstream consumer가 아직 읽는 필드를 섣불리 제거하지 말 것
- read-model 작업을 strategist output 정리보다 먼저 크게 확장하지 말 것

## 2.5 수용 기준
- strategist_output은 “최종 결정문”이 아니라 “전략 proposal package”로 읽혀야 한다
- commander-applied 결과와 strategist proposal이 구분된다
- backward compatibility 유지

## 2.6 테스트/검증
- strategist_output schema regression test
- llm strict/failure metadata regression test
- mirrored commander field visibility test

---

# 3. Task 3 — Scanner compatibility surface 강화

## 3.1 목적
Scanner가 왜 이 종목을 top-1으로 골랐는지, 특히 monitor 호환성을 포함해 설명 가능하게 만든다.

## 3.2 우선 대상 파일
- `graphs/nodes/scanner_node.py`
- scanner scoring 관련 runtime/helpers 파일
- `libs/contracts/agent_outputs.py`

## 3.3 해야 할 일
1. scanner output에서 아래 필드 노출/정리 강화
   - `entry_compatibility_score`
   - `compatibility_bias`
   - `dominant_block_reason`
   - `expected_monitor_block_reason`
   - `soft_penalty`

2. selection reason 문구/구조에 다음 축 포함
   - 전략 적합성
   - practical tradability
   - monitor 호환성

3. 최근 반복 blocker를 compact summary로 남길 것

4. ranked_candidates에도 필요한 compatibility 진단 surface를 반영할 것

## 3.4 하지 말 것
- scanner가 timing engine처럼 동작하게 만들지 말 것
- scanner에서 BUY/WAIT를 직접 결정하지 말 것

## 3.5 수용 기준
- scanner output만 봐도 “좋은 종목”과 “지금 들어가기 쉬운 종목” 사이 판단 근거가 보인다
- monitor blocker 예측이 설명 가능하다

## 3.6 테스트/검증
- compatibility bias regression test
- dominant_block_reason propagation test
- ranked candidates reason surface test

---

# 4. Task 4 — Monitor visibility 강화

## 4.1 목적
Monitor가 BUY/WAIT/HOLD/SELL를 왜 냈는지, 그리고 얼마나 부족했는지 더 명확히 보이게 만든다.

## 4.2 우선 대상 파일
- `libs/runtime/intraday_monitor_signals.py`
- `graphs/nodes/monitor_node.py`
- monitor artifact contract 관련 파일

## 4.3 해야 할 일
1. WAIT 케이스 visibility 강화
   - `primary_failure_axis`
   - `threshold_margins`
   - `signal_evidence`
   - `entry_transition_trace`

2. near-ready surface 강화
   - `reclaim_distance_to_ready`
   - `volume_distance_to_ready`
   - `breakout_distance_to_ready`
   - `transition_readiness_score`

3. policy interpretation visibility 유지/정리
   - `policy_alignment_summary`
   - `policy_interpreter_trace`
   - `chart_structure_decision_hint`
   - `policy_aware_gating`

4. SELL/HOLD에도 compact summary surface가 유지되도록 정리

## 4.4 하지 말 것
- 모니터가 종목을 재선정하게 만들지 말 것
- BUY/WAIT 로직을 전면 교체하지 말 것
- tuning부터 먼저 하지 말고 visibility 먼저 확보할 것

## 4.5 수용 기준
- WAIT에서 “왜 안 샀는지”뿐 아니라 “얼마나 부족한지”가 바로 보여야 한다
- BUY/SELL/HOLD/WAIT 모두 설명 surface가 존재해야 한다

## 4.6 테스트/검증
- wait reason + distance-to-ready regression test
- policy interpretation trace test
- sell/hold observability regression test

---

# 5. Task 5 — trade_read_model 최소 구현

## 5.1 목적
개별 trade lifecycle을 strategist/운영자가 재사용할 수 있는 deterministic read surface로 만든다.

## 5.2 우선 대상 파일
- `libs/reporting/trade_read_model.py` (신규)
- trade story / lifecycle bundle / canonical artifact reader 관련 파일
- 필요 시 scripts/tests

## 5.3 출력 예시 필드
- `trade_id`
- `symbol`
- `entry_ts`
- `exit_ts`
- `hold_duration_sec`
- `pnl`
- `pnl_pct`
- `playbook`
- `entry_reason`
- `exit_reason`
- `primary_blocker_if_no_buy`
- `strategy_policy_source`
- `applied_policy_source`
- `execution_label`
- `data_source`
- `evidence_recovery_used`

## 5.4 구현 원칙
- canonical artifact 우선
- direct artifact 보조
- event log fallback 마지막
- deterministic only

## 5.5 하지 말 것
- trade_read_model에 narrative 생성 넣지 말 것
- LLM 호출 금지

## 5.6 수용 기준
- run/trade 하나를 deterministic object로 재구성 가능해야 한다
- strategist feedback input pack의 원재료로 재사용 가능해야 한다

## 5.7 테스트/검증
- trade lifecycle fixture regression test
- missing artifact fallback test
- evidence_recovery metadata propagation test

---

# 6. Task 6 — daily_summary_read_model 최소 구현

## 6.1 목적
하루치 run/trade를 strategist와 운영자가 읽을 수 있는 aggregate deterministic surface로 만든다.

## 6.2 우선 대상 파일
- `libs/reporting/daily_read_model.py` (신규)
- daily report generator / reporter analysis 관련 파일

## 6.3 출력 예시 필드
- `trading_day`
- `run_count`
- `trade_count`
- `realized_pnl`
- `win_rate`
- `dominant_blockers`
- `monitor_block_distribution`
- `playbook_performance`
- `symbol_performance_summary`
- `strategist_llm_health`

## 6.4 구현 원칙
- aggregate facts only
- deterministic only
- narrative는 여기서 만들지 않는다

## 6.5 수용 기준
- 하루 상태를 숫자/구조로 일관되게 재사용 가능
- daily report narrative나 strategist feedback의 기반이 될 수 있어야 한다

## 6.6 테스트/검증
- daily aggregation regression test
- blocker histogram test
- playbook stats consistency test

---

# 7. Task 7 — symbol_read_model 최소 구현

## 7.1 목적
종목별 누적 패턴을 deterministic surface로 만들어, 장기적으로 strategist memory의 기반으로 사용한다.

## 7.2 우선 대상 파일
- `libs/reporting/symbol_read_model.py` (신규)
- symbol trade report 관련 파일

## 7.3 출력 예시 필드
- `symbol`
- `trade_count`
- `win_rate`
- `avg_pnl_pct`
- `avg_hold_duration`
- `dominant_entry_reason`
- `dominant_exit_reason`
- `dominant_monitor_blocker`
- `recent_success_pattern`
- `repeated_failure_pattern`

## 7.4 구현 원칙
- 종목별 cumulative facts deterministic 집계
- 긴 narrative는 만들지 않는다

## 7.5 수용 기준
- 특정 symbol의 반복 실패/성공 패턴을 deterministic하게 확인 가능
- future strategy memory input의 기반이 될 수 있어야 한다

## 7.6 테스트/검증
- symbol aggregation regression test
- repeated blocker/success pattern summary test

---

# 8. Task 8 — Report fact/narrative boundary 문서화

## 8.1 목적
리포트 전체 agent화보다 먼저, facts와 narrative 경계를 명확히 문서로 고정한다.

## 8.2 우선 대상 파일
- `docs/execution_plan/phase_5_4_execution_plan.md` 보강 또는 별도 문서
- reporting 관련 docs
- 필요 시 tests naming/comments

## 8.3 문서화 대상
### AI Trade Report
- facts deterministic
- retrospective narrative LLM

### Operator Brief
- facts deterministic 위주
- 장중 commentary는 짧고 보수적으로

### Daily Report
- aggregate facts deterministic
- day interpretation / lessons LLM

### Symbol cumulative
- cumulative stats deterministic
- long-horizon behavior summary LLM 선택적

## 8.4 수용 기준
- Codex와 인간이 같은 기준으로 report boundary를 이해 가능해야 함
- future phase 6 작업의 기준 문서가 되어야 함

---

# 9. 장중 검증 이후 실행 순서 추천

## 장중
- 5-3-2 검증
- run_id 확보
- dominant blocker / compatibility mismatch / llm health 확인

## 장후 1차
- Task 1
- Task 2

## 장후 2차
- Task 3
- Task 4

## 장후 3차
- Task 5
- Task 6
- Task 7

## 이후
- Task 8 및 후속 report boundary 정리

---

# 10. 장전 실행 여부 판단 기준

## 원칙
장전에는 **구조 변경 작업을 실행하지 않는 것**을 기본으로 한다.

### 장전에는 해도 되는 것
- 문서 보강
- TODO 정리
- diff 리뷰
- 테스트 계획 준비
- 장중 검증 체크리스트 확정

### 장전에는 하지 않는 것이 좋은 것
- ownership 변경 코드 패치
- route/path 변경
- strategist invocation 조건 변경
- scanner/monitor contract 변경
- reporting pipeline wiring 변경

## 이유
- 장중 검증 전 구조를 바꾸면 5-3-2 검증 결과를 순수하게 보기 어려움
- baseline behavior가 흔들리면 비교가 안 됨
- 장후 수정의 우선순위를 잘못 잡을 수 있음

## 예외
아주 작은 로그/가시성 보강 패치로,
- behavior 불변
- decision 불변
- artifact only additive
가 확실한 경우에만 제한적으로 가능

---

# 11. Codex 전달용 최종 주의사항

Codex는 다음을 지킬 것.

1. **검증 전 대규모 구조 변경 금지**
2. **장중 결과를 먼저 보고 ownership/wiring 수정**
3. **additive + compatibility-first**
4. **문서와 테스트 동반 수정**
5. **facts deterministic / narrative selective LLM**
6. **Commander deterministic 유지**
7. **strict strategist 철학 유지**
   - LLM 없으면 매수 허용 fallback을 이번 단계에서 도입하지 말 것

---

# 12. 최종 한 줄 요약

이번 작업은 새 기능 잔뜩 넣는 작업이 아니다.

- Commander를 상위 owner로 세우고
- Strategist를 proposal owner로 정리하고
- Scanner/Monitor 연결을 더 설명 가능하게 만들고
- Reporting을 “생성”에서 “소비 가능” 상태로 확장하는 작업이다.

Codex는 이 순서를 깨지 말고,  
특히 **장중 검증 이전에는 행동 변화가 있는 패치를 넣지 않는 것**을 기본 원칙으로 삼아야 한다.
