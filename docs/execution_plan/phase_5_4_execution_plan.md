# Phase 5-4 / 6-1 실전 고도화 실행 계획
**대상 저장 경로:** `docs/execution_plan/phase_5_4_execution_plan.md`  
**주 독자:** Codex, 개발자, 운영자  
**문서 목적:** 5-3-2 장중 검증 이후 장외 작업에서, Commander/Strategist/Scanner/Monitor/Reporting을 실전 수준으로 고도화하기 위한 **실행 기준 문서**를 제공한다.

---

# 0. 문서 사용법

이 문서는 설명 문서가 아니라 **실행 문서**다.  
따라서 아래 네 가지를 Codex가 반드시 지켜야 한다.

1. **기존 저장 구조를 깨지 말 것**
   - 특히 `reports/trades/*` 구조는 유지
   - additive 방식 우선
   - canonical artifact 계약은 유지

2. **ownership을 먼저 정리하고 로직 확장은 나중**
   - 5-4의 핵심은 decision expansion이 아니라 **ownership / wiring / routing 정리**
   - 6-1의 핵심은 **read-model / reporting 소비 구조 정리**

3. **장중 검증 결과를 반영 가능한 형태로 수정**
   - why-not-buy
   - scanner-monitor mismatch
   - strategist dependency
   - commander routing
   를 바로 측정할 수 있어야 한다

4. **LLM 사용 범위를 엄격히 통제**
   - Strategist: 전략 proposal용 LLM 유지
   - Reporter: narrative/summary용 LLM 유지
   - Commander: deterministic 유지
   - Read-model: deterministic only

---

# 1. 현재 상태 스냅샷 (As-Is)

현재 시스템은 개념적으로 다음 구조다.

```text
Commander → Strategist → Scanner → Monitor → Supervisor → Executor → Reporter
```

하지만 실제 운영 상태를 정확히 정의하면 아래와 같다.

## 1.1 Commander
- runtime orchestration
- route/path 선택
- cached strategist 사용 여부 판단
- applied policy attach / provenance 기록
- runtime control / resilience / cooldown 관련 조정

### 현재 문제
- 진짜 상위 지휘관이라기보다 **파이프라인 오케스트레이터**
- strategist invocation owner로 완전히 자리잡지 못함
- no-trade posture와 playbook selection ownership이 약함

## 1.2 Strategist
- 시장/뉴스/감성/피드백을 받아 전략 frame 생성
- playbook, themes, scanner guidance, monitor_entry_policy, exit_policy proposal 생성
- 현재 실질적으로 상위 판단 비중이 큼

### 현재 문제
- proposal producer를 넘어 사실상 상위 brain처럼 동작
- LLM strict 모드 영향력이 매우 큼
- commander보다 ownership이 커 보임

## 1.3 Scanner
- 후보군 생성
- 실전 필터
- 전략 적합성 점수화
- monitor 호환성 bias 반영
- top-1 선택

### 현재 문제
- 과거보다 좋아졌지만 여전히
  - 전략적으로 좋아 보이는 종목
  - monitor가 지금 들어갈 수 있는 종목
  사이의 간극이 남아 있음

## 1.4 Monitor
- selected symbol에 대해서만 entry/exit 판단
- VWAP / reclaim / breakout / volume / pullback / extension / confidence 평가
- BUY intent 또는 WAIT reason 생성
- exit 시 hold/sell 판단

### 현재 문제
- 역할은 가장 건강함
- 다만 WAIT가 많고, blocker reason이 특정 축에 과도하게 몰릴 수 있음
- policy-aware gating은 아직 제한적

## 1.5 Reporter
- AI trade report
- operator brief
- daily report
- symbol 누적 리포트(부분)
- recent feedback / strategy memory surface

### 현재 문제
- 생성은 되지만 소비 구조가 약함
- agent라기보다 reporting subsystem
- deterministic facts와 LLM narrative 경계가 완전히 고정되진 않음

---

# 2. 핵심 철학 (이번 작업의 절대 기준)

## 2.1 Commander는 deterministic이어야 한다
Commander는 LLM을 필수 의존성으로 쓰지 않는다.  
Commander의 임무는 아래다.

- strategist 호출 여부 결정
- route/path 결정
- playbook 허용/제한
- applied policy 최종 확정
- no-trade posture 결정
- reroute / refresh / skip 판단

즉 Commander는 **brain이 아니라 control tower**가 아니라,  
정확히는 **일관된 상위 지휘자**여야 한다.

## 2.2 Strategist는 proposal owner다
Strategist는 여전히 중요하다.  
하지만 역할은 아래로 명확히 고정한다.

- market interpretation proposal
- playbook proposal
- scanner guidance proposal
- monitor entry/exit policy proposal

즉 최종 owner가 아니라 **정책 제안자**다.

## 2.3 Scanner는 selection engine이다
Scanner는 종목 선택에 집중한다.

- 후보군 생성
- practical filter
- 점수화
- monitor 호환성 bias
- top-1 선정

## 2.4 Monitor는 selected symbol consumer다
Monitor는 절대 universe 재선정 안 한다.  
selected symbol만 보고 BUY/WAIT/HOLD/SELL 판단을 수행한다.

## 2.5 Read-model은 deterministic only다
리포트 소비용 읽기 모델은 절대 LLM 의존 금지.
- fact stitching
- metrics
- blocker distribution
- playbook performance
- symbol cumulative
는 deterministic으로만 구성한다.

## 2.6 LLM은 해석과 제안에만 쓴다
- Strategist: 전략 proposal
- Reporter: narrative / summary / lesson / recommendation
- 나머지: deterministic

---

# 3. 이번 작업의 목표 상태 (To-Be)

작업 완료 후 목표 상태는 아래다.

```text
Commander = route + strategy invocation + applied policy owner
Strategist = strategy / policy proposal producer
Scanner = top candidate selection engine
Monitor = selected symbol timing / intent engine
Reporter = post-run reporting subsystem
Read-model = deterministic feedback surface
```

---

# 4. 작업 범위

## 4.1 이번 범위에 포함
- Commander ownership 강화
- Strategist role downscoping
- Scanner/Monitor wiring 명확화
- Monitor blocker/near-ready visibility 강화
- 최소 read-model 도입
- reporting facts vs narrative 분리 기반 마련
- 장중/장후 검증 기준 코드/문서화

## 4.2 이번 범위에 포함하지 않음
- Commander LLM 도입
- Monitor 최종 BUY/WAIT 로직 전면 교체
- Report 전체를 agent graph node로 재구성
- monthly/weekly full rollout
- 대규모 UI redesign

---

# 5. 단계별 실행 계획

## Phase 5-3-2 검증 (장중)
이 단계는 코드 변경이 아니라 **증거 수집** 단계다.

### 수집해야 할 관측값
1. `dominant blocker reason`
2. `reclaim_distance_to_ready`
3. `volume_distance_to_ready`
4. `breakout_distance_to_ready`
5. `compatibility_bias` vs 실제 monitor decision
6. `strategist llm status`
7. `route/path`
8. `selected/applied policy provenance`

### 확인 질문
- 왜 매수가 안 나왔나?
- scanner는 왜 그 종목을 뽑았나?
- monitor는 왜 WAIT를 냈나?
- strategist의 playbook과 실제 장 상태가 맞았나?
- commander는 strategist를 왜 호출했나?
- strategist 없이는 절대 못 도는 구조인가?

### 산출물
- 장중 체크 결과 메모
- 주요 run_id 목록
- blocker histogram
- top mismatch 사례 3~5건

---

## Phase 5-4-A: Commander ownership 강화
이 단계가 최우선이다.

### 목표
Commander를 “파이프라인 시작점”이 아니라 **상위 route/policy owner**로 명확히 만든다.

### 구체 작업
1. `commander_decision` 스키마를 owner 관점으로 재정의
   - `market_operating_posture`
   - `strategist_invocation`
   - `strategist_refresh_requested`
   - `strategist_refresh_reason`
   - `allowed_playbooks`
   - `banned_playbooks`
   - `scanner_mission`
   - `monitor_mission`
   - `no_trade_reason_code`
   - `applied_policy_source`
   - `applied_policy_source_chain`

2. route selection을 commander 기준으로 명확히 남김
   - full_cycle
   - cached_strategist
   - scanner_then_monitor
   - monitor_only
   - no_trade_path

3. no-trade posture를 strategist가 아니라 commander 소유로 정리

4. strategist 호출 조건 명시
   - flat이고 전략 필요
   - cached strategist stale
   - scanner 결과 품질 낮음
   - monitor blocker가 반복적
   - commander가 refresh 필요 판단

### 수용 기준
- `commander.json`만 봐도 이번 run의 route와 strategist invocation 이유를 이해할 수 있어야 함
- strategist를 호출하지 않는 path가 문서/코드상 명시되어야 함
- applied policy source chain이 분명해야 함

---

## Phase 5-4-B: Strategist 역할 축소 및 proposal owner화

### 목표
Strategist를 상위 owner가 아니라 proposal producer로 명확히 재정의한다.

### 구체 작업
1. strategist_output 필드 분류
   - proposal fields
   - shared transport fields
   - commander-owned mirrored fields
   로 나눈다

2. 다음 필드는 commander final owner로 재정의
   - final playbook allowance
   - applied policy
   - no-trade posture
   - invocation / refresh

3. Strategist는 다음에 집중
   - market interpretation proposal
   - playbook proposal
   - themes / avoid_themes
   - scanner guidance proposal
   - monitor entry/exit policy proposal
   - policy rationale

4. strategist_output에서 commander mirrored field는 유지하되
   ownership metadata를 분리한다

### 수용 기준
- Strategist 출력만으로 최종 owner가 결정된 것처럼 보이지 않아야 함
- commander_applied_policy가 monitor consumer의 1차 truth로 올라와야 함
- backward compatibility는 additive로 유지

---

## Phase 5-4-C: Scanner/Monitor alignment 정리

### 목표
Scanner가 선정한 종목이 monitor에서 즉시 죽는 비율을 낮춘다.

### 구체 작업
1. scanner output에 다음 필드가 명확히 남도록 정리
   - `entry_compatibility_score`
   - `dominant_block_reason`
   - `expected_monitor_block_reason`
   - `compatibility_bias`
   - `soft_penalty`

2. monitor blocker를 scanner에서 재사용 가능한 형태로 compact summary 생성

3. scanner selection reason에 다음 축을 명시
   - 전략 적합성
   - 실전 적합성
   - monitor 호환성

4. 장중 검증 결과를 바탕으로 compatibility bias scale 재점검

### 수용 기준
- scanner top-1 선정 이유를 설명할 때 monitor 호환성이 빠지지 않아야 함
- “좋지만 지금 못 사는 종목”이 top-1이 되는 비율을 줄이는 방향이 보여야 함
- dominant blocker 통계가 read-model로 집계 가능해야 함

---

## Phase 5-4-D: Monitor visibility / tuning 준비

### 목표
BUY/WAIT의 이유를 더 정확히 설명하고, near-ready 케이스를 운영자가 쉽게 볼 수 있게 한다.

### 구체 작업
1. monitor_output에 반드시 남아야 할 핵심 필드 재확인
   - `primary_failure_axis`
   - `threshold_margins`
   - `signal_evidence`
   - `policy_alignment_summary`
   - `chart_structure_decision_hint`
   - `policy_aware_gating`
   - `entry_transition_trace`

2. 장중 검증에서 blocker가 과도하게 몰리면
   로직 전면 수정이 아니라 **visibility 먼저 강화**

3. near-ready 관측 surface 정리
   - reclaim_distance_to_ready
   - volume_distance_to_ready
   - breakout_distance_to_ready
   - transition_readiness_score

### 수용 기준
- WAIT 케이스에서 “얼마나 부족했는지”를 바로 볼 수 있어야 함
- blocker reason만이 아니라 blocker margin도 남아야 함
- tuning보다 먼저 관측 가능성이 강화되어야 함

---

## Phase 6-1-A: 최소 Read-model 도입
이건 5-4와 병행 가능하다. 다만 최소 범위로 제한한다.

### 목표
리포트를 읽어서 strategist/운영자가 소비할 수 있는 deterministic surface를 만든다.

### 도입 대상 (최소 3개)

#### 1. trade_read_model
필수 필드 예시:
- trade_id
- symbol
- entry_ts / exit_ts
- hold_duration_sec
- pnl / pnl_pct
- playbook
- entry_reason
- exit_reason
- primary_blocker_if_no_buy
- strategy_policy_source
- applied_policy_source
- execution_label
- data_source
- evidence_recovery_used

#### 2. daily_summary_read_model
필수 필드 예시:
- trading_day
- run_count
- trade_count
- realized_pnl
- win_rate
- dominant_blockers
- playbook_performance
- symbol_performance_summary
- strategist_llm_health
- monitor_block_distribution

#### 3. symbol_read_model
필수 필드 예시:
- symbol
- trade_count
- win_rate
- avg_pnl_pct
- avg_hold_duration
- dominant_entry_reason
- dominant_exit_reason
- dominant_monitor_blocker
- recent_success_pattern
- repeated_failure_pattern

### 절대 규칙
- read-model은 deterministic only
- canonical artifact 우선
- direct artifact 보조
- event log fallback은 마지막

### 수용 기준
- strategist가 읽을 수 있는 compact input pack으로 변환 가능해야 함
- UI/리포트/배치가 같은 deterministic source를 공유할 수 있어야 함

---

## Phase 6-1-B: Reporting 정리 기반 만들기

### 목표
기존 리포트를 agent화하기보다, facts / narrative / consumer를 분리한다.

### 리포트별 원칙

#### 1. AI Trade Report
- facts: deterministic
- narrative / lessons: LLM
- lifecycle retrospective 중심

#### 2. Operator Brief
- facts: deterministic 위주
- 짧은 운영 comment만 LLM 선택적 사용
- 장중 triage 중심

#### 3. Daily Report
- aggregate facts: deterministic
- day interpretation / strategist feedback: LLM
- 장후 회고 중심

#### 4. Symbol Cumulative
- cumulative stats: deterministic
- long-term behavior summary: LLM 선택적 사용

### 수용 기준
- facts와 narrative 경계가 문서/코드로 명확해야 함
- 리포트끼리 같은 사실을 다르게 말하지 않아야 함
- read-model과 연결 가능한 구조여야 함

---

# 6. 컴포넌트별 상세 계획

## 6.1 Commander 상세 계획

### 해야 할 것
- strategist invocation 조건 표준화
- no-trade posture의 explicit owner화
- playbook allow/ban 표면화
- commander_applied_policy를 1차 truth로 강화
- path 결정 근거 기록

### 하지 말아야 할 것
- 세부 scanner bias 직접 생성
- 세부 monitor 수치 직접 생성
- LLM 도입

### 검증 포인트
- commander only로 이해 가능한 run route
- strategist skip path 존재
- refresh 이유 설명 가능

---

## 6.2 Strategist 상세 계획

### 해야 할 것
- proposal 역할 명확화
- JSON contract 안정화
- policy proposal / rationale / theme interpretation 유지
- commander context를 받되 final owner처럼 보이지 않게 조정

### 하지 말아야 할 것
- final no-trade owner처럼 행동
- applied policy owner처럼 행동
- commander invocation owner처럼 행동

### 검증 포인트
- strategist_output은 proposal package로 읽혀야 함
- commander-applied 결과와 구분 가능해야 함

---

## 6.3 Scanner 상세 계획

### 해야 할 것
- top-1 selection reason에 monitor compatibility 포함
- dominant_block_reason compact summary 남기기
- candidate reduction trace 유지
- repeated symbol penalty / practical filter 유지

### 하지 말아야 할 것
- monitor처럼 timing 판단
- universe selection 후 재전략화까지 직접 수행

### 검증 포인트
- scanner 1순위 선정 이유에 “왜 지금 이 종목인가”가 있어야 함
- compatibility bias가 설명 가능해야 함

---

## 6.4 Monitor 상세 계획

### 해야 할 것
- BUY/WAIT/HOLD/SELL reason compact + detailed surface 유지
- margin / readiness 기반 관측 강화
- policy source chain 노출 강화

### 하지 말아야 할 것
- 종목 재선정
- commander 역할 흡수
- execution 역할 침범

### 검증 포인트
- WAIT 사유뿐 아니라 distance-to-ready가 보여야 함
- SELL/HOLD 이유가 일관된 source에서 나오도록 유지

---

## 6.5 Reporting 상세 계획

### 해야 할 것
- report 생성 로직보다 read-model 우선
- 사실/집계 deterministic 고정
- LLM은 summary / lesson / recommendation에 한정

### 하지 말아야 할 것
- raw event log를 각 report가 제각각 직접 해석
- 같은 사실의 중복 재조립
- report를 지금 당장 graph agent로 재구성

### 검증 포인트
- 같은 run/trade를 여러 리포트가 읽어도 facts가 일치해야 함
- strategist feedback input이 deterministic pack에서 나와야 함

---

# 7. 테스트 / 검증 계획

## 7.1 장중 검증 체크리스트
1. `commander route/path`
2. `strategist invocation / refresh`
3. `scanner top-1 reason`
4. `entry_compatibility_score`
5. `monitor dominant blocker`
6. `distance_to_ready`
7. `llm_frame_status`
8. `applied_policy_source_chain`

## 7.2 장후 검증 체크리스트
1. trade 발생 여부
2. no-trade 이유 분포
3. blocker histogram
4. playbook별 성과
5. symbol별 반복 실패 패턴
6. strategist feedback pack 생성 가능 여부

## 7.3 회귀 테스트 초점
- reports/trades 구조 비파괴
- canonical artifact 스키마 additive 유지
- strategist strict 철학 유지
- commander deterministic 유지
- read-model deterministic only 유지

---

# 8. Codex 작업 원칙

Codex는 아래 원칙으로 작업해야 한다.

## 8.1 작은 패치 우선
대규모 재작성 금지.
- additive
- compatibility first
- feature flag / metadata first

## 8.2 source-of-truth 명시
모든 새 필드는 owner를 먼저 정의할 것.
예:
- final owner
- proposal owner
- consumer
- mirrored transport

## 8.3 문서와 테스트 같이 수정
구조를 건드렸다면 반드시
- 문서
- 테스트
- artifact validation
을 같이 업데이트할 것.

## 8.4 LLM 확장 금지
이번 단계에서 Commander LLM화 금지.
read-model LLM화 금지.
report facts LLM화 금지.

---

# 9. 최종 산출물 요구사항

이번 작업이 끝나면 최소 아래 산출물이 있어야 한다.

1. `commander ownership`이 강화된 문서/코드
2. `strategist proposal owner`가 반영된 필드 구조
3. `scanner-monitor alignment` 설명 가능한 artifact
4. `trade_read_model`
5. `daily_summary_read_model`
6. `symbol_read_model` 최소 버전
7. report fact/narrative 경계 문서
8. 장중/장후 검증 체크리스트 반영

---

# 10. 최종 요약

이번 작업은 로직을 더 복잡하게 만드는 단계가 아니다.  
핵심은 다음 네 가지다.

1. **Commander를 진짜 상위 owner로 세운다**
2. **Strategist를 proposal owner로 내린다**
3. **Scanner-Monitor 연결을 설명 가능하게 만든다**
4. **Reporting을 생성 시스템에서 소비 시스템으로 확장한다**

즉,  
**5-4는 ownership/wiring 정리 단계이고,  
6-1은 read-model/reporting consumption 기초를 세우는 단계다.**

이 문서를 기준으로 작업하면,  
장중 검증 결과를 장후에 바로 구조 개선으로 연결할 수 있어야 한다.
