# M17 Graph Spine + Risk Branch

## 목표
- 7개 에이전트 역할에 맞는 **그래프 뼈대(spine)** 를 고정한다.
- `risk_score`/`confidence` 기반 **리스크 분기(approve/reject/retry_scan)** 를 구현하고 테스트로 고정한다.
- 기존 테스트와의 호환을 위해 `selected / intents[0] / risk` 등 입력 경로를 방어적으로 지원한다.

## Graph 순서(기본)
1. Commander: 전체 사이클 오케스트레이션
2. Strategist: trade plan + candidates 생성
3. Scanner: 후보별 데이터/피처 계산 + selected 선택
4. Monitor: **OrderIntent만 생성**
5. Supervisor: 리스크 검증 + 승인(2-phase)
6. Executor: 승인된 intent 실행
7. Reporter: 사후 리포트

## 주요 state 필드
- `policy`: 운영 정책(예: max_risk, min_confidence, max_scan_retries)
- `candidates`: 3~5 후보 리스트 `[{symbol, why}, ...]`
- `scan_results`: 후보별 결과 dict
- `selected`: 최종 선택 `{"symbol":..., "score":..., "risk_score":..., "confidence":...}`
- `intents`: (하위 호환) 의도 리스트. 일부 테스트/주입에서 사용
- `retry_count_scan`: 스캔 재시도 카운터

## Decision 규칙
- `risk_score > policy.max_risk` → `reject`
  - `decision_reason="risk_too_high"`
- `confidence < policy.min_confidence` →
  - retry 가능하면 `retry_scan` (`decision_reason="low_confidence_retry"`)
  - retry 소진이면 `reject` (`decision_reason="low_confidence_reject"`)
- 그 외 → `approve` (`decision_reason="within_policy"`)

## Retry Scan
- `max_scan_retries`에 도달할 때까지 `scanner`를 재호출한다.
- 재호출 시 stale 값(이전 risk/confidence)을 참조하지 않도록
  - 우선순위: `selected` → `intents[0]` → `risk` 순으로 참조.

## 테스트 포인트
- 리스크가 너무 높으면 reject + reason이 정확
- confidence가 낮으면 1회 retry 후 개선 시 approve
- Monitor는 intent 생성만(계산/선정 금지)
