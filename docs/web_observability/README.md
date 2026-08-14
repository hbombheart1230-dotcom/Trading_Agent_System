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
6. `isolation_and_modularity_contract.md`
   - mandatory Trading Runtime isolation rules
   - backend/frontend module boundaries
   - bounded-resource and no-side-effect gates
   - per-slice verification checklist
7. `product_data_contract_v1.md`
   - time, truth, cost-basis, and performance definitions
   - missing-data and availability semantics
   - internal/public data boundaries
8. `combined_milestone_plan_2026-08-14.md`
   - product goal and information architecture
   - Q9-Q18 and current-research data mapping
   - generic read models and API surface
   - implementation milestones M0-M9
9. `read_only_ui_docker_kubernetes_review_2026-08-14.md`
   - repository and infrastructure review
   - read-only and import-isolation constraints
   - Docker/Compose/Kubernetes design details

The product is not an evaluation-progress dashboard. It presents performance,
trades, opportunities, strategies, market context, reports, and data-quality
signals. Evaluation artifacts are internal evidence sources.

No document in this folder authorizes trading, evaluation, prompt, execution,
or runtime behavior changes.
