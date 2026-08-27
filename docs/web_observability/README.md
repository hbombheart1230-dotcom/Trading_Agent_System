# Web Observability and Portfolio UI

This folder owns the design for the independent read-only operating and
portfolio presentation layer.

Current authority:

1. `implementation_status_2026-08-14.md`
   - completed and pending milestone status
   - test and live-runtime non-interference evidence
2. `m2_source_audit_2026-08-14.md`
   - accepted performance and portfolio sources
   - rejected malformed raw snapshot surface
   - explicit unsupported metric boundary
3. `m3_trade_source_audit_2026-08-14.md`
   - full-bundle and performance-fallback authority
   - timeline integrity and report allowlist
   - historical display coverage
4. `m4_opportunity_strategy_market_source_audit_2026-08-14.md`
   - shadow opportunity and forward-outcome boundaries
   - strategy breakdown authority and coverage
   - market snapshot and series source contract
5. `m5_web_ui_implementation_2026-08-14.md`
   - product pages and frontend module boundaries
   - local execution and browser verification
   - UI safety and read-only behavior
6. `m5_1_llm_operations_implementation_2026-08-14.md`
   - OpenRouter role and actual-model visibility
   - stage call, bounded latency, and token availability semantics
   - prompt, response, credential, and path exclusion
7. `m6_anomaly_public_profile_implementation_2026-08-14.md`
   - explainable operations anomaly rules
   - server-enforced public showcase and redaction boundary
   - public/private metric parity
8. `isolation_and_modularity_contract.md`
   - mandatory Trading Runtime isolation rules
   - backend/frontend module boundaries
   - bounded-resource and no-side-effect gates
   - per-slice verification checklist
9. `m7_prerequisites_and_weekend_plan_2026-08-14.md`
   - verified Windows/WSL/Docker prerequisite state
   - weekend Compose implementation and validation slices
   - current and future Trading Runtime container boundary
10. `m7_docker_compose_implementation_2026-08-18.md`
   - implemented API/Web images and Compose profiles
   - read-only mounts, non-root services, and resource isolation
   - completed Docker Engine, private/public profile, browser, and isolation gates
11. `m7_engine_gate_2026-08-26.md`
   - installed host tools and post-restart Linux Engine verification
   - engine-discovered corrections and final M7 evidence
12. `m7_1_main_runtime_visibility_2026-08-27.md`
   - minimal Windows Trading Main visibility in the read-only Docker UI
   - heartbeat, logical process tree, duplicate-session, and market expectation rules
   - explicit no-control and no-runtime-container boundary
13. `m7_2_host_supervisor_2026-08-27.md`
   - bounded Windows Trading Main automatic recovery policy
   - immutable watchdog decision history and operator UI
   - restart cooldown, daily limit, and read-only API boundary
14. `m7_3_scheduled_intelligence_2026-08-27.md`
   - existing Preopen/Closeout result materialization without duplicate LLM calls
   - memory delivery receipt and active/advisory semantics
   - scheduled job status and briefing visibility in Overview
15. `product_data_contract_v1.md`
   - time, truth, cost-basis, and performance definitions
   - missing-data and availability semantics
   - internal/public data boundaries
16. `combined_milestone_plan_2026-08-14.md`
   - product goal and information architecture
   - Q9-Q18 and current-research data mapping
   - generic read models and API surface
   - implementation milestones M0-M9
17. `read_only_ui_docker_kubernetes_review_2026-08-14.md`
   - repository and infrastructure review
   - read-only and import-isolation constraints
   - Docker/Compose/Kubernetes design details

The product is not an evaluation-progress dashboard. It presents performance,
trades, opportunities, strategies, market context, LLM operations, reports,
and data-quality signals. Evaluation artifacts are internal evidence sources.

M7.1 adds one operational exception to that product summary: a compact,
read-only Trading Main status. It normalizes Windows parent/child processes to
one logical session and exposes no start, stop, restart, kill, or order action.

M7.2 keeps that UI read-only while extending the existing Windows scheduled
watchdog with bounded recovery for stopped, heartbeat-stale, duplicated, and
ownership-inconsistent Main sessions. Every watchdog decision is retained as
history and shown on Overview; the API still exposes no control endpoint.

M7.3 reuses the existing Preopen and Closeout pipelines to materialize an
operator briefing, daily intelligence index, scheduled job manifests and a
memory delivery receipt. It adds no scheduler task and no LLM call.

No document in this folder authorizes trading, evaluation, prompt, execution,
or runtime behavior changes.
