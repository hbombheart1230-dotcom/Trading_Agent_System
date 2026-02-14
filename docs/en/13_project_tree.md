# 13. Project Tree

- Last updated: 2026-02-14
- Scope: high-level repository layout for implementation and operations.

## Top-Level Layout

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

## Key Areas

- `graphs/`: runtime orchestration nodes and pipeline entry points.
- `libs/`: domain implementation (strategist/scanner/monitor/supervisor/execution/reporting).
- `scripts/`: smoke/demo/ops scripts.
- `tests/`: regression and milestone tests.
- `docs/ground_rules/`: non-negotiable rules and quality gates.
- `docs/plan/`: milestone implementation notes.

## M20-Related Documents

- `docs/plan/m20_1_llm_smoke_and_fallback.md`
- `docs/plan/m20_2_schema_retry_telemetry.md`
- `docs/plan/m20_3_legacy_llm_router_compat.md`
- `docs/plan/m20_4_smoke_and_llm_event_query.md`
- `docs/en/12_roadmap.md`
- `docs/ko/12_roadmap.md`
- `docs/ground_rules/AGENT_RULES.md`
- `docs/ground_rules/QUALITY_GATES.md`

## Note

- This document intentionally stays high-level.
- For detailed runtime contracts and flows, use:
  - `docs/runtime/state_contract.md`
  - `docs/io_contracts.md`
  - `docs/architecture/system_flow.md`
