# M20-M30 Integrated Plan (7-Agent, LangGraph, Skills)

- Date: 2026-02-14
- Scope: Commander, Strategist, Scanner, Monitor, Supervisor, Executor, Reporter
- Goal: move from M20 LLM reliability to M30 production-grade autonomous operations with strict safety gates.

## 1) Baseline (as of M20)

- M20-1 ~ M20-6 completed (LLM reliability, adapter parsing, schema normalization, retry/telemetry, metrics).
- Current runtime has two coexisting paths:
  - Graph spine path: `graphs/trading_graph.py`
  - Decision/execution packet path: `graphs/nodes/decide_trade.py` -> `graphs/nodes/execute_from_packet.py`
- LangGraph formal model is specified, but runtime is not yet fully consolidated into a single StateGraph execution entry.

## 2) Planning Principles (non-negotiable)

1. LLM is advisory only; never direct execution authority.
2. Supervisor/guards always override strategy intent.
3. Execution idempotency is mandatory (`intent_id` must not execute twice).
4. DTO/schema contracts are versioned and backward-compatible.
5. Every milestone must keep mock-safe testability and operator observability.

## 3) Milestone Roadmap (M20 -> M30)

## M20 (Done): LLM Strategist Reliability

- Completed:
  - OpenRouter adapter parsing (content -> JSON -> normalized intent)
  - retry/backoff + attempts metadata
  - strategist LLM telemetry (`stage=strategist_llm`)
  - ops smoke/query scripts + daily metrics integration
  - prompt/schema version telemetry

## M21: Commander-Centric LangGraph Consolidation

- Objective:
  - unify orchestration into one formal graph runtime.
- Deliverables:
  - implement concrete `StateGraph` runtime entry (single run loop)
  - map nodes: commander_router -> strategist -> scanner -> monitor -> supervisor -> executor -> reporter
  - formalize retry/cancel/pause transitions in code (not docs-only)
  - deprecate duplicate orchestration path where possible
- Exit criteria:
  - one canonical runtime entry for automated runs
  - parity tests pass for existing M20 behavior

## M22: Skill-Native Scanner/Monitor Upgrade

- Objective:
  - make Scanner/Monitor consume composite skills as primary data path.
- Deliverables:
  - Scanner uses `market.quote`, `account.orders` and candidate feature extraction via skill outputs
  - Monitor uses `order.status` for live intent lifecycle tracking
  - standardize skill DTO consumption contracts in nodes
  - add quality gates for skill timeout/error fallback behavior
- Exit criteria:
  - Scanner/Monitor logic no longer depends on ad-hoc payload shapes
  - skill failure modes are observable and recoverable

## M23: Runtime Resilience (Circuit Breaker + Safe Degrade)

- Objective:
  - prevent cascading failures during provider/API instability.
- Deliverables:
  - circuit breaker for strategist/provider failures
  - safe degrade mode (rule-only strategist fallback, execution tightening)
  - incident counters + cooldown policy in Commander routing
  - runbook entries for operator intervention/resume
- Policy freeze (2026-02-17):
  - when `degrade_mode=true`, force effective approval to manual (`auto` approval disabled)
  - tighten execution notional in degrade mode to 25% of normal guardrail (`degrade_notional_ratio=0.25`)
  - require non-empty symbol allowlist in degrade mode; if allowlist is missing/empty, block execution
- Exit criteria:
  - repeated upstream errors do not trigger uncontrolled retries/execution attempts

## M24: Execution Safety Hardening

- Objective:
  - strengthen execution guardrails and idempotency guarantees.
- Deliverables:
  - strict intent journal state machine (`pending_approval -> approved -> executing -> executed/failed`)
  - duplicate-intent execution block + replay-safe semantics
  - stronger real-mode preflight checks and explicit denial reasons
  - regression tests for guard precedence and partial-failure scenarios
- Storage strategy decision (2026-02-17):
  - adopt a dedicated intent state store (SQLite-first; KV compatible) as primary source of truth
  - keep event log (`JSONL`) append-only for audit/replay/rebuild, but not as the only live duplicate-check path
  - provide reconciliation tooling (`intent_store` <-> event log) for recovery drills
- Exit criteria:
  - idempotency and guard precedence proven by automated tests

## M25: Observability and Alerting Operations

- Objective:
  - move from logs to actionable operations visibility.
- Deliverables:
  - run-level and stage-level SLI metrics (latency/success/failure/retries)
  - alert policy for critical events (guard spikes, strategist failure rate, execution anomalies)
  - dashboard-ready exports and scheduled report artifacts
  - metric schema freeze for downstream tooling
- Minimum metric set freeze (2026-02-17):
  - strategist_llm: `success_rate`, `latency_p95`, `circuit_open_rate`
  - execution: `intents_created`, `intents_approved`, `intents_blocked`, `intents_executed`, `blocked_reason_topN`
  - broker/api: `api_error_total_by_api_id`, `api_429_rate`
- Exit criteria:
  - operators can detect and triage incidents without code inspection

## M26: Strategy Evaluation Framework

- Objective:
  - validate strategy quality before execution expansion.
- Deliverables:
  - offline replay/backtest harness with fixed datasets
  - comparable strategy scorecards (PnL proxy, risk-adjusted metrics, drawdown)
  - A/B evaluation support for prompt/schema versions
  - acceptance thresholds for promotion to live candidates
- Exit criteria:
  - strategy changes require measurable evidence before promotion

## M27: Multi-Strategy / Portfolio Allocation

- Objective:
  - scale from single-path decisions to portfolio-level orchestration.
- Deliverables:
  - multiple strategy profiles and allocation policies
  - conflict resolution for simultaneous intents
  - portfolio risk budgeting at Commander/Supervisor boundary
  - policy simulation tests (overlap, concentration, exposure limits)
- Exit criteria:
  - concurrent strategy outputs stay within portfolio guardrails

## M28: Deployment and Runtime Platformization

- Objective:
  - standardize deployment lifecycle for reliable operations.
- Deliverables:
  - containerized runtime profiles (dev/staging/prod)
  - scheduler/worker topology and safe startup/shutdown hooks
  - secret/config profile separation and environment validation
  - rollout checklist and rollback procedure
- Exit criteria:
  - repeatable deployment with deterministic startup behavior

## M29: Governance, Audit, and Recovery

- Objective:
  - enterprise-grade traceability and recovery readiness.
- Deliverables:
  - audit trail completeness checks (intent->decision->execution linkage)
  - log archival/retention policy and integrity checks
  - incident timeline reconstruction tooling
  - disaster recovery drill (restore + replay validation)
- Exit criteria:
  - complete run trace reconstruction is possible from stored artifacts

## M30: Production Readiness Gate

- Objective:
  - formal go-live readiness with measurable gates.
- Deliverables:
  - final quality gates bundle (functional, resilience, safety, ops)
  - fail-safe validation in real-mode dry-run and controlled pilot
  - release sign-off checklist (architecture, security, operations)
  - post-go-live monitoring and escalation policy
- Exit criteria:
  - all mandatory gates green and sign-off complete

## 4) 7-Agent Capability Progression Map

- Commander:
  - M21 graph unification, M23 incident routing, M27 portfolio routing
- Strategist:
  - M20 reliability complete, M26 evaluation/A-B governance
- Scanner:
  - M22 skill-native feature pipeline
- Monitor:
  - M22 order-status driven lifecycle monitoring
- Supervisor:
  - M24 strict guard/idempotency enforcement, M27 portfolio risk budget
- Executor:
  - M24 execution safety hardening, M28 runtime platform integration
- Reporter:
  - M25 dashboards/alerts, M29 audit/recovery reporting

## 5) Suggested Delivery Rhythm

- M21-M24: architecture and safety foundation
- M25-M27: operations and strategy scaling
- M28-M30: platform/governance/go-live gates

## 6) Immediate Next Action

1. Start M21 implementation branch with one canonical StateGraph runtime entry.
2. Freeze current node IO contracts before refactor.
3. Add migration tests that assert behavior parity vs current M20 path.
