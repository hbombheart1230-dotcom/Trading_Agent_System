# Trading Agent Alignment 문서 묶음

이 폴더는 `docs/roadmap/`의 단계별 진행 문서를 대체하지 않는다.  
역할은 다르다.

- `docs/roadmap/`: 무엇을 왜 어떤 순서로 바꿀지에 대한 단계별 설계/종결 노트
- `docs/alignment/`: 지금 시스템이 실제로 무엇인지, 각 에이전트가 무엇을 맡는지, 어떤 스키마를 주고받는지, 남은 단계에서 ownership을 어떻게 정리할지를 한 번에 보는 운영 기준 문서

## 왜 새 폴더로 분리했나

이번 문서의 목적은 “새 기능 설계”보다 **현재 상태를 정확히 정의하고 ownership을 맞추는 것**이다.  
그래서 기존 roadmap 아래에 더 얹기보다 `docs/alignment/`처럼 성격이 분명한 폴더로 분리하는 편이 낫다.

## 문서 구성

1. `01_glossary_and_core_terms.md`
   - 핵심 용어집
   - 역할/상태/아티팩트/정책 관련 기본 정의

2. `02_current_system_definition_as_is.md`
   - 현재 시스템의 as-is 정의
   - 현재 구조에서 무엇이 이미 정리되었고 무엇이 아직 migration 중인지

3. `03_agent_roles_inputs_outputs_and_handoffs.md`
   - Commander, Strategist, Scanner, Monitor, Supervisor, Executor, Reporter
   - 각 역할의 목적 / 입력 / 출력 / 비책임 / handoff 정리

4. `04_contracts_source_of_truth_and_schema_surfaces.md`
   - canonical artifact, strategy/scanner/monitor/supervisor 계약
   - source-of-truth 표
   - 정책/리포팅/관측 계층 간 연결 정리

5. `05_gap_analysis_and_plan_5_4_to_6.md`
   - 현재와 목표의 차이
   - 5-3-2 이후 5-4와 6에서 정리해야 할 ownership과 wiring
   - Commander / Strategist / Reporter 방향성 정리

## 읽는 순서 추천

- 처음 한 번 정독: 01 → 02 → 03 → 04 → 05
- 장중 점검 직전: 02 → 03 → 04
- 설계 리팩토링 시작 전: 03 → 04 → 05
