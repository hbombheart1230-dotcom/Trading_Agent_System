# Reporter 재구조화 및 운영 실행 계획
기준일: 2026-04-15

## 목적

이 문서는 Reporter를 단순한 LLM JSON 생성기에서, 결정론적 Fact와 LLM Narrative를 분리한 진짜 에이전트로 재구조화하기 위한 실행 문서다.

핵심 원칙은 다음과 같다.

1. 이미 개발된 자산은 버리지 않는다.
2. 새로운 구조는 기존 자산 위에 재조합한다.
3. 모든 경로는 동일한 입력 계약을 사용해야 한다.
4. Fact는 코드가 결정하고, Narrative만 LLM에 위임한다.
5. 문서 close가 아니라 운영 close를 기준으로 판단한다.

---

## 배경 요약

현재 시스템에는 이미 다음 자산이 존재한다.

- Commander 중심 오케스트레이션 구조
- Strategist / Scanner / Monitor / Supervisor / Executor의 canonical artifact
- trade_story_pipeline 기반 trade story input 계층
- ai_trade_report / operator brief / same-day reporter analysis
- strategist가 재소비할 수 있는 read-model 계층
- lifecycle bundle 및 canonical artifact 경로
- Reporter 관련 LLM Router, JSON salvage, fallback/merge 체계

문제는 기능이 없어서가 아니라, 다음 세 가지로 정리된다.

1. report generation 경로가 여러 개로 분기되면서 동일 contract가 유지되지 않았다.
2. lifecycle 재조립에서 provenance / canonical path / normalized trace가 충분히 살아남지 못했다.
3. Reporter가 사실(Fact)과 서사(Narrative)를 동시에 LLM에 맡기면서 trade_report_ai.py가 과도하게 비대해졌다.

즉, 현 상태는 “새로 만들어야 하는 시스템”이 아니라 “이미 만든 시스템을 단일 입력 계약 위로 정렬해야 하는 시스템”이다.

---

## 최종 목표 구조

최종적으로 Reporter는 다음 4단 구조를 가져야 한다.

1. Read Model Layer
2. Reporter Agent Layer
3. Rendering / Adapter Layer
4. Consumer Layer

### 1. Read Model Layer

단일 거래 lifecycle을 기준으로 결정론적 Fact를 추출한다.

출력 예시:

- facts
- provenance
- deterministic summaries
- structured rationale

### 2. Reporter Agent Layer

Read Model을 입력으로 받아 LLM에게 Narrative만 생성하게 한다.

LLM이 생성하는 값은 다음 범위로 제한한다.

- summary
- bullets
- lessons
- operator-facing explanation

LLM이 생성하면 안 되는 값:

- symbol
- trade_id
- pnl
- pnl_pct
- entry_ts
- exit_ts
- exit trigger
- policy source
- canonical path
- provenance

### 3. Rendering / Adapter Layer

Reporter Agent의 출력과 기존 artifact 형식을 연결한다.

역할:

- json/md 렌더링
- backward-compatible field mapping
- UI / 기존 스크립트 소비 포맷 유지

### 4. Consumer Layer

다음 소비자가 Reporter 산출물을 읽는다.

- Operator
- Strategist read-model
- Commander retrospective / policy diagnostics
- future daily reporter / meta-reporter

---

## 남길 것 / 고정할 것 / 미룰 것

### 남길 것

#### A. 사용자 관점의 trade report narrative 구조
유지한다.

이유:
- 이미 market context, why selected, entry, holding, exit, execution, evaluation의 틀이 잘 형성되어 있다.
- 사용자 관점 설명 방식은 자산이다.

#### B. trade_story_pipeline 계층
유지하되 역할을 조정한다.

이유:
- 여전히 lifecycle normalization과 section provenance 생성에 유용하다.
- 다만 LLM용 sparse input 공장 역할은 줄인다.

#### C. strategist / trade read-model 축
유지 및 확장한다.

이유:
- Reporter의 Fact source로 재사용 가능하다.
- 이후 Strategist feedback loop의 기반이다.

#### D. Commander 중심 통솔 구조
유지한다.

이유:
- 경로 분기나 설정 권한 집중 원칙과 일치한다.
- Reporter도 Commander의 orchestration 아래에서 동작하는 것이 맞다.

### 고정할 것

#### A. 공통 입력 계약
모든 report generation 경로는 반드시 같은 입력 계약을 사용해야 한다.

필수 필드:

- canonical_agent_artifacts
- evidence_provenance
- artifacts.canonical_*_json
- scanner_selection_trace
- monitor_stop_policy_trace
- monitor_blocker_trace
- same_day_reporter_linkage

#### B. canonical-first source priority
Read Model은 반드시 아래 우선순위를 강제해야 한다.

1. canonical artifacts
2. lifecycle bundle normalized facts
3. event-derived recovery
4. legacy report fallback

#### C. provenance를 1급 필드로 승격
새 Reporter 출력의 최상위에 provenance를 둔다.

#### D. empty placeholder overwrite 규칙
빈 dict/list/string/null placeholder는 “값 있음”이 아니라 “미채움”으로 취급한다.

#### E. 운영 close 기준
문서 close와 별도로 운영 close를 둔다.

### 미룰 것

#### A. Reporter 추가 에이전트화
critic loop, self-review, autonomous diagnosis는 미룬다.

#### B. Strategist 자동 피드백 강화
read-model 재소비는 유지하되, 자동 정책 반영은 뒤로 미룬다.

#### C. LLM 호출 최적화
다중 재시도나 prompt 튜닝은 뒤 단계다.

#### D. UI 개선
contract가 안정된 뒤 진행한다.

---

## 구현 전략

### 전략 1. trade_report_ai.py를 당장 삭제하지 않는다
단, 장기적으로는 adapter로 축소한다.

현재 역할 분해 목표:

- 사실 추출: trade_read_model.py
- narrative 생성: reporter agent
- 렌더링/호환: trade_report_ai.py

### 전략 2. read_model을 공식 Reporter State로 승격한다
build_trade_read_model(trade_dir)는 Reporter Agent의 공식 입력이 된다.

최종 반환 구조 권장안:

```python
{
    "facts": {...},
    "provenance": {...},
    "context": {...},
    **facts
}
```

여기서 `**facts`는 과도기적 backward compatibility 용도다.
최종적으로는 facts/provenance/context 중심 접근으로 수렴시킨다.

### 전략 3. Narrative-only LLM contract 채택
LLM에게는 아래만 생성하게 한다.

```json
{
  "executive_summary": {"summary": ""},
  "market_context": {"summary": "", "bullets": []},
  "why_selected": {"summary": "", "bullets": []},
  "entry_story": {"summary": "", "bullets": []},
  "holding_and_exit": {"summary": "", "bullets": []},
  "lessons_learned": {"bullets": []}
}
```

금지:
- metadata echo
- 수치 재계산
- provenance 재판단

---

## 단계별 실행 계획

## Phase R1. Reporter Read Model 완성

### 목표
build_trade_read_model()을 Reporter Agent의 신뢰 가능한 State로 만든다.

### 수정 대상
- libs/reporting/trade_read_model.py

### 핵심 작업
1. canonical-first source priority 강제
2. facts/provenance 분리
3. scanner / monitor / executor / strategist 핵심 rationale 추가
4. derived fields 정리
5. backward compatibility 유지

### facts에 포함할 최소 필드
- trade_id
- symbol
- entry_ts
- exit_ts
- hold_duration_sec
- pnl
- pnl_pct
- playbook
- entry_reason
- exit_reason
- execution_label
- primary_blocker_if_no_buy
- applied_policy_source
- strategy_policy_source
- evidence_recovery_used

### 추가할 context 권장 필드
- scanner_selection_summary
- scanner_score_drivers
- scanner_top_candidates
- monitor_entry_reason
- monitor_exit_trigger
- thresholds_snapshot
- watch_axes
- same_day_reporter_status
- data_source_quality

### provenance에 기록할 최소 필드
각 fact별 source string

예:
- canonical.strategist
- canonical.monitor
- canonical.executor
- lifecycle_bundle.entry
- lifecycle_bundle.exit
- legacy_report
- derived
- fallback_default

### Phase R1 완료 조건
- 테스트 통과
- build_trade_read_model()이 facts/provenance를 반환
- 동일 trade에서 source priority가 재현 가능
- canonical이 있으면 legacy보다 먼저 선택됨

---

## Phase R2. Reporter Agent 진입점 신설

### 목표
Reporter를 독립 agent function 또는 node로 분리한다.

### 수정 대상
- libs/agent/reporter.py 또는 graphs/nodes/reporter_node.py
- 필요 시 libs/reporting/trade_report_ai.py 일부 adapter wiring

### 권장 함수 시그니처
```python
run_reporter_agent(trade_dir: str, policy: dict) -> dict
```

### 내부 단계
1. read_model = build_trade_read_model(trade_dir)
2. read_model 유효성 검사
3. LLM 메시지 생성
4. narrative-only template 기반 응답 파싱
5. final output 조립
6. json/md artifact 저장 또는 adapter 반환

### 최종 출력 구조 권장안
```python
{
    "metadata": {
        "trade_id": "...",
        "symbol": "...",
        "generated_by": "reporter_agent_v1"
    },
    "facts": {...},
    "provenance": {...},
    "narrative": {...},
    "status": "ok"
}
```

### Phase R2 완료 조건
- Reporter Agent가 단독 실행 가능
- LLM 실패 시 facts/provenance는 유지
- narrative만 빈 template로 fallback 가능

---

## Phase R3. trade_report_ai.py Adapter화

### 목표
거대한 legacy fallback/merge 코드를 점진적으로 비우고 adapter 역할만 남긴다.

### 수정 대상
- libs/reporting/trade_report_ai.py

### 역할 재정의
기존:
- 사실 추출
- sparse story input 생성
- LLM 호출
- JSON repair
- fallback merge
- 렌더링

미래:
- reporter agent 호출
- 출력 렌더링
- 기존 호출부 호환 유지

### Adapter에서 남겨야 할 것
- md/json 렌더링
- 기존 호출부 호환
- 최소한의 compatibility mapping

### 제거 대상(최종)
- LLM에게 Fact까지 echo시키는 template
- 과도한 merge/fallback candidate 조립
- giant sparse story input 가공

### Phase R3 완료 조건
- 기존 호출부가 adapter를 통해 동작
- 내부 실제 생성 로직은 reporter agent로 이관
- giant fallback 코드가 신규 경로에서 더 이상 사용되지 않음

---

## Phase R4. 경로 단일화

### 목표
bundle path, single-trade path, regeneration path 모두 Reporter Agent 공통 경로를 사용하게 한다.

### 수정 대상
- scripts/run_live_execution_bundle_report.py
- libs/reporting/single_trade_report.py
- graphs/commander_runtime.py
- 기타 targeted generation 스크립트

### 원칙
- 모든 경로는 최종적으로 build_trade_read_model 또는 공통 bundle contract를 거친다
- helper가 얇은 bundle_out를 직접 조립하지 않는다
- evidence_provenance가 비면 fail-fast 또는 explicit degraded status를 남긴다

### Phase R4 완료 조건
- single/bundle/regeneration path 결과 구조 동일
- provenance 붕괴 없음
- section_provenance fallback 비율이 예외 수준으로 감소

---

## Phase R5. 운영 Close

### 목표
문서 close가 아니라 실제 운영 close를 달성한다.

### 검증 파일
- lifecycle_bundle.json
- ai_trade_report_input.json 또는 신규 reporter agent input
- ai_trade_report.json
- ai_trade_report.md

### 운영 합격 기준
1. closed trade 3건 이상에서 재현
2. facts/provenance 구조 안정
3. scanner/monitor provenance가 무조건 fallback으로 내려가지 않음
4. scanner_selection_trace.ranked_candidates 존재
5. monitor_stop_policy_trace 존재
6. same-day reporter file 없으면 expected/found로 정직하게 표시
7. LLM 실패 시에도 facts/provenance 산출물은 유지
8. old/new 비교에서 신규 경로가 최소 동등 이상 품질

---

## 구체 구현 세부안

## 1. trade_read_model.py 구현 가이드

### 주의사항
- return은 마지막 한 번만
- facts/provenance와 legacy dict return을 혼합하지 말 것
- canonical = bundle.get("canonical_agent_artifacts") or {} 로 안전 초기화
- derived field는 facts 기준으로 계산
- backward compatibility가 필요하면 `**facts`를 같이 반환
- applied_policy_source는 commander와 monitor를 분리하거나 priority를 명확히 할 것

### 권장 구조
```python
return {
    "facts": facts,
    "provenance": provenance,
    "context": context,
    **facts,
}
```

### context 권장 예시
```python
context = {
    "scanner": {...},
    "monitor": {...},
    "strategist": {...},
    "executor": {...},
    "same_day_reporter_linkage": {...}
}
```

---

## 2. Reporter Agent 구현 가이드

### 금지 사항
- raw story_input를 그대로 LLM에 던지지 말 것
- symbol/pnl/time 같은 metadata echo를 요구하지 말 것
- narrative와 fact를 섞어 반환하게 하지 말 것

### 허용 사항
- facts/context를 compact json으로 LLM에 제공
- template는 narrative-only
- parse 실패 시 빈 narrative template 사용

---

## 3. trade_report_ai adapter 구현 가이드

### 1차 목표
기존 외부 호출부는 유지하고 내부만 reporter agent로 위임

### 2차 목표
기존 huge fallback 함수들을 deprecated 처리

### 3차 목표
신규 경로 안정화 후 old giant path 제거

---

## 테스트 계획

## 필수 테스트 1. Read Model source priority
- canonical / lifecycle / legacy 충돌 시 canonical 우선 검증

## 필수 테스트 2. provenance completeness
- 핵심 facts 모두 provenance를 가짐

## 필수 테스트 3. Reporter Agent resilience
- LLM 실패 시 facts/provenance는 유지

## 필수 테스트 4. single/bundle parity
- 동일 trade에서 single path와 bundle path가 동등한 facts를 반환

## 필수 테스트 5. same-day reporter honesty
- reporter file 없으면 artifact_path가 비고 expected/found만 남음

## 필수 테스트 6. regression
- 2026-04-10 유사 정상 사례와 2026-04-14 유사 회귀 사례를 fixture로 비교

---

## Codex 실행 지침

### 1차 작업 지시
- libs/reporting/trade_read_model.py만 수정
- facts/provenance/context 구조 도입
- 테스트 추가
- 외부 호출부 깨지지 않게 backward compatibility 유지

### 2차 작업 지시
- libs/agent/reporter.py 신설
- run_reporter_agent(trade_dir, policy) 구현
- narrative-only LLM contract 도입
- 테스트 추가

### 3차 작업 지시
- trade_report_ai.py를 adapter 경로로 연결
- old/new 비교 가능한 feature flag 또는 내부 switch 추가
- 기존 giant logic는 유지하되 신규 호출부에서는 reporter agent 우선 사용

### 4차 작업 지시
- single/bundle/regeneration path를 reporter agent 공통 경로로 정렬
- 운영 검증 3건 수행

---

## 실행 순서 권장안

1. R1: trade_read_model 완성
2. R2: reporter agent 신설
3. R3: trade_report_ai adapter화
4. R4: 경로 단일화
5. R5: 운영 close
6. 그 다음에야 reporter 추가 agentization / strategist feedback 강화

---

## 지금 당장 하지 말 것

- trade_report_ai.py 전면 삭제
- prompt만 계속 만지기
- LLM 호출 횟수 늘리기
- UI부터 붙이기
- reporter critic loop 먼저 만들기

---

## 최종 판단

현재 가장 효율적인 개발 방향은 “최소 수정”이 아니라 “기존 자산 재조합을 통한 구조 최적화”다.
다만 그 방식은 무질서한 대규모 변경이 아니라, read-model → reporter agent → adapter → path unification 순서로 진행해야 한다.

이 문서대로 가면 다음이 가능해진다.

- Reporter를 진짜 에이전트로 승격
- trade_report_ai giant fallback 구조 해체
- Strategist read-model 재소비 안정화
- Commander 중심 orchestration과 일관된 report generation 경로 확보
- 운영 close 기준으로 검증 가능한 구조 확립
