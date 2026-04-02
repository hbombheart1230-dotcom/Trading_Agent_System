# Phase 5-3 Close Note - Policy-Driven Monitor Foundation

## 1. Goal

Phase 5-3의 원래 목표는 strategist가 정의한 전략(policy)을 Monitor가 직접 읽을 수 있게 만들어,
Monitor를 threshold-heavy rule engine에서 policy-aware / policy-driven 방향으로 이동시키는 foundation을 만드는 것이었다.

이 phase의 핵심은 final BUY/WAIT ownership을 즉시 완전히 옮기는 것이 아니라,
정책 source, 해석 surface, evidence surface, narrow integration까지를 먼저 고정하는 데 있었다.

## 2. Background Problem

Phase 5-3 시작 전 상태의 핵심 문제는 아래와 같았다.

- entry 조건과 threshold가 많고 경직적이었다.
- shadow scoring이 별도 decision layer처럼 보일 위험이 있었다.
- policy sourcing과 provenance가 암묵적이었다.
- Monitor 해석이 playbook fallback에 많이 의존했다.
- evidence / trace / summary surface가 부족해서 non-UI consumer나 후속 wiring이 읽기 어려웠다.

## 3. What Phase 5-3 Completed

### A. Shadow scoring ownership cleanup

shadow scoring은 독립 decision layer에서 내려오고, Monitor 내부 evidence/scoring helper로 재정의되었다.

- scoring은 final BUY/WAIT owner가 아니다.
- scoring은 signal evidence 계산과 trace 용도로 남는다.

### B. Evidence / interpretation / trace surfaces

이번 phase에서 아래 surface가 추가되었다.

- `signal_evidence`
  - reclaim / volume / pullback / breakout / confidence 관련 score, check, derived 상태를 담는 evidence surface
- `policy_interpretation`
  - policy를 Monitor가 읽기 쉬운 required / preferred / relaxable / blocker 축으로 정리한 interpretation surface
- `policy_interpreter_trace`
  - interpretation과 evidence를 연결해서 현재 cycle의 pass/fail/alignment를 보여주는 trace surface
- `policy_alignment_summary`
  - full trace를 compact하게 요약하는 summary surface

이 surface들은 final owner가 아니라 explanation / consumption surface다.

### C. First narrow policy-aware gating integration

policy-driven decision migration의 첫 integration으로, breakout 상황의 reclaim near-ready에 대해서만 매우 제한적인 완화가 도입되었다.

이 integration은 broad relaxation이 아니라 narrow policy-aware exception이다.

- reclaim gate 한 종류만 제한적으로 고려한다.
- required failure, extension, confidence, supporting path 같은 안전 조건은 그대로 유지한다.
- threshold rewrite, multi-gate relaxation, required bypass는 하지 않는다.

### D. Explicit policy sourcing contract

Monitor가 policy source를 명시적으로 읽도록 아래 contract가 도입되었다.

- `build_monitor_entry_policy_contract(...)`
- `contract_version = "monitor_entry_policy_contract.v1"`
- `selected_source`
- `selected_policy`
- `source_priority`
- `sources`

이 contract는 Monitor가 어떤 source를 실제로 선택했는지와, 어떤 source들이 후보로 있었는지를 explicit하게 보여준다.

### E. Explicit policy consumer structure

Monitor interpretation은 더 이상 playbook / notes 중심의 암묵적 해석기에만 머물지 않고,
`entry_policy_contract.selected_policy`를 우선 읽는 explicit policy consumer 구조로 옮겨졌다.

- explicit field가 있으면 그것을 우선 사용한다.
- playbook / notes / rationale은 fallback으로 남는다.

### F. Explicit interpretation field schema stabilization

selected_policy의 loose field를 안정적으로 읽기 위해 normalized schema candidate가 추가되었다.

- `normalize_monitor_entry_policy_schema(...)`
- `schema_version = "monitor_entry_policy_schema_candidate.v1"`

이 단계는 semantic expansion이 아니라 shape stabilization이다.

- loose string / list / tuple / set 입력을 list-like field로 정리한다.
- partial dict를 known key 중심으로 정리한다.
- 없는 의미를 새로 발명하지 않는다.

## 4. Current Structure

현재 5-3 종료 시점의 Monitor 구조는 아래와 같다.

```text
policy sources
-> entry_policy_contract
-> selected_policy
-> selected_policy_schema
-> policy_interpretation
-> signal_evidence
-> policy_interpreter_trace
-> policy_alignment_summary
-> narrow policy_aware_gating
-> legacy gates
-> final BUY/WAIT
```

중요한 점은 final BUY/WAIT owner가 아직 `legacy gates`라는 것이다.

5-3은 foundation / contract / narrow integration까지를 수행했고,
full ownership migration까지는 의도적으로 가지 않았다.

## 5. Contracts, Schemas, and Surfaces

### Policy source contract

- `monitor_entry_policy_contract.v1`

이 contract는 policy source selection과 provenance를 explicit하게 고정한다.

### Policy schema candidate

- `monitor_entry_policy_schema_candidate.v1`

이 schema candidate는 `selected_policy`의 explicit interpretation field를 normalized shape로 안정화한다.

### Interpretation provenance

`policy_interpretation`은 아래 provenance 성격 필드를 노출한다.

- `interpretation_basis`
- `contract_source`
- `explicit_fields_used`
- `policy_schema_available`
- `policy_schema_version`
- `policy_schema_raw_keys`

즉 현재 cycle interpretation이 explicit policy에서 왔는지, fallback playbook인지, mixed인지가 드러난다.

### Alignment / explanation surfaces

아래 surface는 explanation / consumption 용도다.

- `signal_evidence`
- `policy_interpreter_trace`
- `policy_alignment_summary`

이들은 final decision owner가 아니다.

## 6. Source of Truth and Responsibility Boundary

이번 phase는 새로운 source of truth를 만드는 단계가 아니었다.

- source of truth:
  - existing policy sources
  - `entry_policy_contract.selected_policy`
  - existing monitor checks and thresholds
- interpretation / exposure layer:
  - `selected_policy_schema`
  - `policy_interpretation`
  - `signal_evidence`
  - `policy_interpreter_trace`
  - `policy_alignment_summary`
  - `policy_aware_gating`

즉 5-3은 기존 truth를 policy-aware Monitor가 읽기 좋게 정리한 phase다.

## 7. Intentionally Not Done

이번 phase에서 의도적으로 하지 않은 것은 아래와 같다.

- final decision ownership을 legacy gate에서 완전히 옮기지 않았다.
- broad multi-gate relaxation을 하지 않았다.
- threshold rewrite를 하지 않았다.
- required check bypass를 하지 않았다.
- strategist policy generation 방식을 바꾸지 않았다.
- commander ownership을 바꾸지 않았다.
- runtime wiring을 하지 않았다.
- UI / data_access 연결을 하지 않았다.
- non-UI consumer 연결을 하지 않았다.
- LLM summary / recommendation layer를 붙이지 않았다.

즉 5-3은 foundation / contract / narrow integration까지이고, full migration은 아니다.

## 8. Why Phase 5-3 Can Be Closed Here

Phase 5-3은 아래 이유로 close 가능하다.

- policy source contract가 생겼다.
- `selected_policy` preferred 구조가 생겼다.
- normalized schema candidate가 생겼다.
- interpretation / evidence / trace / summary / narrow gating이 모두 연결되었다.
- final owner는 legacy gate로 남겨 안전성을 유지했다.

따라서 5-3의 핵심 목표는 "policy-driven Monitor foundation 구축" 관점에서 달성되었다고 볼 수 있다.

이후 남은 작업은 5-3 핵심 구현이라기보다 아래 성격에 더 가깝다.

- contract freeze 이후 wiring
- ownership transition planning
- broader policy-driven decision migration
- later-stage phase 5-4 expansion

## 9. Natural Next Steps

이번 문서에서 구현하지는 않지만, 다음으로 자연스러운 작업은 아래와 같다.

- runtime wiring / non-UI consumer connection
- ownership transition planning
- policy schema formalization beyond candidate
- broader policy-driven decision migration
- phase 5-4 planning

## 10. One-Line Conclusion

Phase 5-3은 policy-driven Monitor로 가기 위한 foundation, contract, provenance, explanation surface, narrow policy-aware integration까지를 확보한 상태이며,
final BUY/WAIT ownership migration은 다음 phase의 작업으로 남겨 두었다.
