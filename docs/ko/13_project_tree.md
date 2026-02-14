# 13. 프로젝트 트리

- 최종 업데이트: 2026-02-14
- 범위: 구현/운영 관점의 저장소 상위 구조 요약

## 상위 구조

```text
Trading_Agent_System/
  config/
    .env.example
    skills/
  data/
    logs/
    originals/
    specs/
  docs/
    en/
    ko/
    architecture/
    ground_rules/
    plan/
    runtime/
  graphs/
    nodes/
    pipelines/
  libs/
    agent/
    ai/
    catalog/
    core/
    execution/
    kiwoom/
    read/
    reporting/
    risk/
    runtime/
    skills/
    storage/
    supervisor/
    tools/
  scripts/
  tests/
  README.md
  requirements.txt
  auto_push.bat
```

## 핵심 영역

- `graphs/`: 런타임 오케스트레이션 노드/파이프라인
- `libs/`: 도메인 구현(전략/스캔/모니터/감독/실행/리포팅)
- `scripts/`: 운영/스모크/데모 스크립트
- `tests/`: 회귀 및 마일스톤 테스트
- `docs/ground_rules/`: 비타협 규칙과 품질 게이트
- `docs/plan/`: 현재 마일스톤 구현 메모 (`docs/plan/archive/`에 M3-M7 레거시 문서 보관)

## M20 관련 문서

- `docs/plan/m20_1_llm_smoke_and_fallback.md`
- `docs/plan/m20_2_schema_retry_telemetry.md`
- `docs/plan/m20_3_legacy_llm_router_compat.md`
- `docs/plan/m20_4_smoke_and_llm_event_query.md`
- `docs/plan/m20_5_llm_metrics_dashboard.md`
- `docs/plan/m20_6_prompt_schema_version_telemetry.md`
- `docs/en/12_roadmap.md`
- `docs/ko/12_roadmap.md`
- `docs/ground_rules/AGENT_RULES.md`
- `docs/ground_rules/QUALITY_GATES.md`

## 참고

- 본 문서는 의도적으로 상위 구조만 유지합니다.
- 상세 계약/흐름 문서는 아래를 참조합니다.
  - `docs/runtime/state_contract.md`
  - `docs/io_contracts.md`
  - `docs/architecture/system_flow.md`
