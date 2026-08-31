# Supervisor "modify" Contract Gap (문서-코드 불일치 기록)

## 요약

문서는 Supervisor의 판정을 `approve | reject | modify` 3-state로 정의하지만, 실제 구현된 판정 함수는 `approve`/`reject`에 해당하는 boolean 결과만 반환하며 `modify` 개념이 코드 어디에도 존재하지 않는다. Phase 1(Execution Safety Alignment)에서는 이 gap을 **구현하지 않고** 별도 기록으로만 분리한다.

## 문서 측 주장

- [docs/io_contracts.md](../io_contracts.md) `## SupervisorDecision`: `approve | reject | modify`, `modifications` (optional) 필드를 명시.
- [docs/alignment/03_agent_roles_inputs_outputs_and_handoffs.md](../alignment/03_agent_roles_inputs_outputs_and_handoffs.md) `## 7. Supervisor`: "OrderIntent를 승인/거절/수정한다", "수정 내역(있다면)"을 주요 출력으로 명시.
- [docs/ground_rules/AGENT_RULES.md](../ground_rules/AGENT_RULES.md) `## 2) Role Boundaries`: "Validates OrderIntent and **approves / rejects / modifies**."

## 코드 측 실제 상태

- 실제 라이브 실행 경로(`graphs/nodes/execute_from_packet.py`)에서 호출되는 `libs/risk/supervisor.py::Supervisor.allow(intent: str, context: dict) -> AllowResult`는 다음 dataclass만 반환한다:
  ```python
  @dataclass(frozen=True)
  class AllowResult:
      allow: bool
      reason: str
      details: Dict[str, Any]
  ```
  (`libs/risk/supervisor.py:10-14`)
- `allow` 필드는 boolean이며, `reject` 사유는 `reason`/`details`로 설명될 뿐 "수정된 intent"를 반환하는 경로가 없다.
- `libs/risk/supervisor.py` 전체에서 `modify`를 검색하면 매치되는 것은 클래스 docstring 한 줄(`"...must not modify env or configs."` — 이는 Supervisor 자신이 설정을 수정하면 안 된다는 무관한 문장)뿐이며, intent를 수정하는 로직·필드·분기는 전무하다(`libs/risk/supervisor.py:20`).
- `libs/runtime/host_supervisor.py:17`에 별도 `SupervisorDecision` dataclass가 존재하지만, 이는 `graphs/commander_runtime.py`의 라이브 실행 경로와 무관한 별도 컴포넌트이며 이 gap을 해소하지 않는다(미조사, 별도 확인 필요).

## Phase 1에서의 처리 방침

- `modify` 기능은 **구현하지 않는다** — 현재 실행 경로 어디에도 "수정된 intent"를 실제로 사용하는 소비자가 없어, 구현 시 사용처 없는 죽은 코드가 될 위험이 크고, Phase 1의 범위(Execution Safety Alignment)를 벗어난다.
- 이 문서는 향후 (a) `modify`가 실제로 필요한 유스케이스가 생기거나, (b) 문서를 코드에 맞춰 `approve|reject` 2-state로 정정하기로 결정할 때 참고할 근거로 남긴다.
- 별도 결정 없이는 `docs/io_contracts.md` 등 기존 계약 문서 자체는 수정하지 않는다(문서 정정 여부는 이 gap 인지 이후 별도 논의 사항).

## 관련

- 검증 근거: 2026-08-31 세션의 AS-IS runtime architecture 검증 (항목 6: Supervisor approve/reject/modify enforcement — MISMATCH)
- 관련 계획: Phase 1 Execution Safety Alignment plan, Step 1
