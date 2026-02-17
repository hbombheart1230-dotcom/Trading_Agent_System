# 13. Project Tree

- Last updated: 2026-02-17
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
- `docs/plan/m22_4_skill_dto_contract_standardization.md`
- `docs/plan/m22_5_skill_hydration_node.md`
- `docs/plan/m22_6_graph_hydration_wiring.md`
- `docs/plan/m22_7_hydration_smoke_gate.md`
- `docs/plan/m22_8_auto_composite_runner_connection.md`
- `docs/plan/m22_9_hydration_metrics_reporting.md`
- `docs/plan/m22_10_closeout_and_handover.md`
- `scripts/demo_m22_skill_flow.py`
- `scripts/demo_m22_skill_hydration.py`
- `scripts/demo_m22_graph_with_hydration.py`
- `scripts/smoke_m22_hydration.py`
- `scripts/run_m22_closeout_check.py`
- `tests/test_m22_10_closeout_check.py`

## M23-Related Documents

- `docs/plan/m23_1_runtime_resilience_state_contract.md`
- `docs/plan/m23_2_runtime_circuit_breaker_core.md`
- `docs/plan/m23_3_strategist_runtime_circuit_integration.md`
- `docs/plan/m23_4_commander_incident_cooldown_routing.md`
- `docs/plan/m23_5_safe_degrade_execution_policy.md`
- `docs/plan/m23_6_operator_intervention_resume_runbook.md`
- `docs/plan/m23_7_commander_resilience_ops_visibility.md`
- `docs/plan/m23_8_resilience_closeout_and_handover.md`
- `docs/plan/m23_9_commander_resilience_metrics_reporting.md`
- `docs/plan/m23_10_closeout_and_m24_handover.md`
- `docs/plan/m24_1_intent_journal_state_machine_sqlite.md`
- `docs/plan/m24_2_approval_flow_sqlite_state_integration.md`
- `docs/plan/m24_3_duplicate_execution_claim_guard.md`
- `docs/plan/m24_4_intent_state_reconciliation_tooling.md`
- `docs/plan/m24_5_real_execution_preflight_denial_reasons.md`
- `docs/plan/m24_6_guard_precedence_regression_bundle.md`
- `docs/plan/m24_7_intent_state_ops_visibility.md`
- `libs/runtime/resilience_state.py`
- `libs/runtime/circuit_breaker.py`
- `libs/supervisor/intent_state_store.py`
- `libs/approval/service.py`
- `graphs/nodes/execute_from_packet.py`
- `graphs/commander_runtime.py`
- `scripts/query_commander_resilience_events.py`
- `scripts/run_m23_resilience_closeout_check.py`
- `scripts/generate_metrics_report.py`
- `scripts/run_m23_closeout_check.py`
- `scripts/reconcile_intent_state_store.py`
- `scripts/query_intent_state_store.py`
- `scripts/check_real_execution_preflight.py`
- `scripts/run_m24_guard_precedence_check.py`
- `tests/test_m23_1_runtime_resilience_state_contract.py`
- `tests/test_m23_2_runtime_circuit_breaker_core.py`
- `tests/test_m23_3_decide_trade_runtime_circuit_integration.py`
- `tests/test_m23_4_commander_incident_cooldown_routing.py`
- `tests/test_m23_5_safe_degrade_execution_policy.py`
- `tests/test_m23_6_operator_intervention_resume.py`
- `tests/test_m23_7_commander_resilience_ops_script.py`
- `tests/test_m23_8_resilience_closeout_check.py`
- `tests/test_m23_9_commander_resilience_metrics_report.py`
- `tests/test_m23_10_closeout_check.py`
- `tests/test_m24_1_intent_state_store.py`
- `tests/test_m24_2_approval_state_store_integration.py`
- `tests/test_m24_3_duplicate_execution_claim_guard.py`
- `tests/test_m24_4_intent_state_reconcile_script.py`
- `tests/test_m24_5_real_execution_preflight.py`
- `tests/test_m24_6_guard_precedence_check.py`
- `tests/test_m24_7_intent_state_ops_query.py`

## Note

- This document intentionally stays high-level.
- For detailed runtime contracts and flows, use:
  - `docs/runtime/state_contract.md`
  - `docs/io_contracts.md`
  - `docs/architecture/system_flow.md`
