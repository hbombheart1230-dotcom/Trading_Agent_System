# 13. Project Tree

- Last updated: 2026-02-15
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
- `docs/plan/`: active milestone implementation notes (`docs/plan/archive/` stores legacy M3-M7 notes).

## M20-Related Documents

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

## M21-Related Documents

- `docs/plan/m21_1_canonical_runtime_entry.md`
- `docs/plan/m21_2_runtime_mode_resolution_policy.md`
- `docs/plan/m21_3_decision_packet_activation_guard.md`
- `docs/plan/m21_4_runtime_transitions.md`
- `docs/plan/m21_5_runtime_agent_chain_mapping.md`
- `docs/plan/m21_6_runtime_once_cli.md`
- `docs/plan/m21_7_commander_router_event_logging.md`
- `docs/plan/m21_8_graph_spine_parity_tests.md`
- `docs/plan/m21_9_commander_bridge_to_canonical_runtime.md`

## M22-Related Documents

- `docs/plan/m22_1_skill_native_scanner_monitor_baseline.md`
- `docs/plan/m22_2_monitor_order_lifecycle.md`
- `docs/plan/m22_3_skill_timeout_error_quality_gates.md`
- `scripts/demo_m22_skill_flow.py`

## Note

- This document intentionally stays high-level.
- For detailed runtime contracts and flows, use:
  - `docs/runtime/state_contract.md`
  - `docs/io_contracts.md`
  - `docs/architecture/system_flow.md`
