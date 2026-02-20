# Document Index (Enterprise Spec)

This set is an **enterprise-grade architecture specification** covering
operations, security, governance, and extensibility.

## Structure
1. 01_overview.md — Vision and system overview
2. 02_principles.md — Principles and non-negotiable rules
3. 03_context_and_scope.md — Scope / non-scope / assumptions
4. 04_logical_architecture.md — Logical architecture (layers/components)
5. 05_runtime_flow.md — Runtime flows (sequence/state machine)
6. 06_contracts.md — IO contracts / DTO / schema stability
7. 07_execution_and_guards.md — Execution control / guards / approvals
8. 08_observability.md — Observability (logs/metrics/audit)
9. 09_security_and_compliance.md — Security / compliance / secrets
10. 10_deployment_and_ops.md — Deployment / operations / runbooks (SLO/alerts)
11. 11_testing_and_quality.md — Testing / quality / regression strategy
12. 12_roadmap.md — Roadmap (M16+ approve API, LangGraph formalization, etc.)
13. 13_project_tree.md — Project tree and key implementation map
14. 99_glossary.md — Glossary

## Program Plans
- docs/plan/m20_to_m30_master_plan.md -> Integrated roadmap through M30
- docs/plan/m31_to_m36_post_golive_plan.md -> Post-go-live roadmap through M36
- docs/plan/m20_7_token_cost_telemetry.md -> M20-7 token/cost telemetry milestone
- docs/plan/m21_1_canonical_runtime_entry.md -> M21 canonical runtime start
- docs/plan/m21_10_docs_sync_closeout.md -> M21 closeout/documentation sync
- docs/plan/m22_1_skill_native_scanner_monitor_baseline.md -> M22-1 skill-native scanner/monitor baseline
- docs/plan/m22_2_monitor_order_lifecycle.md -> M22-2 monitor lifecycle mapping
- docs/plan/m22_3_skill_timeout_error_quality_gates.md -> M22-3 skill timeout/error fallback quality gates
- docs/plan/m22_4_skill_dto_contract_standardization.md -> M22-4 shared skill DTO contract adapter
- docs/plan/m22_5_skill_hydration_node.md -> M22-5 skill hydration node for scanner/monitor pipeline
- docs/plan/m22_6_graph_hydration_wiring.md -> M22-6 graph spine hydration wiring
- docs/plan/m22_7_hydration_smoke_gate.md -> M22-7 hydration pass/fail smoke gate
- docs/plan/m22_8_auto_composite_runner_connection.md -> M22-8 auto composite runner connection
- docs/plan/m22_9_hydration_metrics_reporting.md -> M22-9 hydration/fallback metrics reporting integration
- docs/plan/m22_10_closeout_and_handover.md -> M22-10 closeout check and M23 handover
- docs/plan/m23_1_runtime_resilience_state_contract.md -> M23-1 runtime resilience state contract scaffold
- docs/plan/m23_2_runtime_circuit_breaker_core.md -> M23-2 runtime circuit breaker core and tests
- docs/plan/m23_3_strategist_runtime_circuit_integration.md -> M23-3 strategist runtime circuit integration in decide path
- docs/plan/m23_4_commander_incident_cooldown_routing.md -> M23-4 commander incident counter and cooldown routing
- docs/plan/m23_5_safe_degrade_execution_policy.md -> M23-5 degrade-mode execution tightening policy
- docs/plan/m23_6_operator_intervention_resume_runbook.md -> M23-6 operator intervention/resume control and runbook
- docs/plan/m23_7_commander_resilience_ops_visibility.md -> M23-7 commander resilience event query CLI for operator visibility
- docs/plan/m23_8_resilience_closeout_and_handover.md -> M23-8 resilience closeout check and handover
- docs/plan/m23_9_commander_resilience_metrics_reporting.md -> M23-9 commander resilience metrics reporting integration
- docs/plan/m23_10_closeout_and_m24_handover.md -> M23-10 final closeout and M24 handover
- docs/plan/m24_1_intent_journal_state_machine_sqlite.md -> M24-1 strict intent state machine and SQLite store scaffold
- docs/plan/m24_2_approval_flow_sqlite_state_integration.md -> M24-2 ApprovalService integration with SQLite intent state transitions
- docs/plan/m24_3_duplicate_execution_claim_guard.md -> M24-3 duplicate execution claim guard with SQLite CAS
- docs/plan/m24_4_intent_state_reconciliation_tooling.md -> M24-4 JSONL/SQLite intent state reconciliation tooling
- docs/plan/m24_5_real_execution_preflight_denial_reasons.md -> M24-5 real execution preflight and explicit denial reason codes
- docs/plan/m24_6_guard_precedence_regression_bundle.md -> M24-6 guard precedence regression bundle
- docs/plan/m24_7_intent_state_ops_visibility.md -> M24-7 intent state/journal ops visibility query and stuck-executing gate
- docs/plan/m24_8_closeout_and_m25_handover.md -> M24-8 final closeout and M25 handover
- docs/plan/m25_1_metric_schema_freeze_v1.md -> M25-1 metric schema freeze v1 and validation gate
- docs/plan/m25_2_alert_policy_threshold_gate.md -> M25-2 alert policy threshold gate
- docs/plan/m25_3_alert_reporting_closeout.md -> M25-3 alert reporting artifacts and closeout gate
- docs/plan/m25_4_alert_policy_env_profile.md -> M25-4 env-backed alert policy profile and runbook
- docs/plan/m25_5_ops_batch_hook.md -> M25-5 scheduler-ready ops batch hook with lock/status artifact
- docs/plan/m25_6_alert_channel_adapter.md -> M25-6 webhook alert channel adapter and batch notification integration
- docs/plan/m25_7_notification_noise_control.md -> M25-7 notification dedup/rate-limit noise control
- docs/plan/m25_8_slack_webhook_provider.md -> M25-8 Slack incoming-webhook provider integration
- docs/plan/m25_9_notification_retry_policy.md -> M25-9 bounded notification retry/backoff policy
- docs/plan/m25_10_notification_event_log_and_query.md -> M25-10 notification event log and query CLI
- docs/plan/m26_1_fixed_dataset_manifest_scaffold.md -> M26-1 fixed dataset manifest scaffold and validation gate
- docs/plan/m26_2_replay_runner_scaffold.md -> M26-2 fixed dataset replay runner scaffold
