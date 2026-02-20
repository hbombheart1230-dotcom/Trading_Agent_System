# 12. Roadmap (M16+)

## M16: Formal approval API
- approve(intent_id) / reject(intent_id) / preview(intent_id)
- fully reproducible manual approval mode

## M17: Settings single source of truth
- make approval_mode an official Settings field
- remove direct env lookups (one canonical path)

## M18: LangGraph formal orchestration
- map agent roles to nodes under graphs/
- define transitions/retries/cancellation policies

## M19+: Stronger ops stack
- metrics dashboards
- alerting policy (Slack/Email)
- audit log archiving

## M20: LLM Strategist Reliability
- M20-1:
  - provider smoke coverage (config/timeout/response-shape)
  - decide_trade integration smoke with safe fallback
  - operator smoke script for strategist-only validation (no execution)
- M20-2:
  - OpenRouter chat-completions adapter parsing (content JSON extraction -> intent shape)
  - canonical intent schema normalization before decision handoff
  - transient retry/backoff policy with attempt metadata
  - strategist LLM event telemetry (`stage=strategist_llm`)
- M20-3:
  - restore legacy `libs.llm.router` compatibility import (`ChatMessage`)
  - add regression tests for legacy router import/payload path
- M20-4:
  - smoke CLI options for strategist LLM event visibility (`--show-llm-event`, `--require-llm-event`)
  - operator query CLI for `strategist_llm` result events
- M20-5:
  - include strategist LLM reliability metrics in daily metrics report
  - add success-rate/latency/attempts/error-type aggregates for operator dashboards
- M20-6:
  - attach `prompt_version` / `schema_version` to strategist LLM telemetry
  - add version distribution metrics (`prompt_version_total`, `schema_version_total`)
- M20-7:
  - add strategist LLM token usage telemetry (`prompt_tokens`, `completion_tokens`, `total_tokens`)
  - add optional estimated cost telemetry (`estimated_cost_usd`) from env-configured token prices
  - extend ops scripts and daily metrics report with token/cost aggregates

## M21-M30 (Program Plan)
- M21: Commander-centric LangGraph consolidation (single canonical graph runtime)
- M22: skill-native Scanner/Monitor upgrade (`market.quote`, `account.orders`, `order.status`)
- M23: runtime resilience (circuit breaker + safe degrade mode)
- M24: execution safety hardening (strict idempotency and guard precedence)
- M25: observability and alerting operations (SLIs/SLO-ready metrics)
- M26: strategy evaluation framework (replay/backtest + promotion gates)
- M27: multi-strategy portfolio allocation and conflict resolution
- M28: deployment/runtime platformization (container + scheduler + rollback)
- M29: governance/audit/recovery readiness (archive, integrity, DR drills)
- M30: production readiness gate (final safety/ops sign-off)

## M31-M36 (Post-GoLive Program Plan)
- M31: post-go-live stabilization (SLO calibration, on-call escalation, incident loop)
- M32: performance and cost optimization (latency/token/API budget tuning)
- M33: capital allocation and risk expansion (portfolio-aware sizing and budgets)
- M34: market/broker expansion (multi-broker contract and failover policy)
- M35: governance/compliance automation (policy-as-code and signed audit bundles)
- M36: autonomous operations and self-healing (automated recovery and adaptive guards)

M21 implementation status (2026-02-15):
- M21-1: canonical commander runtime entry (`graphs/commander_runtime.py`)
- M21-2: deterministic runtime mode resolution policy (explicit > state > env > default)
- M21-3: activation guard for `decision_packet` mode from state/env routing
- M21-4: runtime transitions formalized (`retry/pause/cancel`)
- M21-5: 7-agent runtime chain mapping in `runtime_plan`
- M21-6: canonical runtime once CLI (safe smoke default)
- M21-7: commander router event logging (`route/transition/end`)
- M21-8: graph-spine parity tests against legacy path
- M21-9: legacy `Commander` bridge to canonical runtime (`run_canonical`)
- M21-10: documentation sync and closeout

M21 phase note (2026-02-17):
- phase 1 complete: canonical runtime entry + bridge + parity
- phase 2 pending: internal runtime migration to LangGraph `StateGraph` while preserving canonical runtime contracts

M22 implementation status (2026-02-16, complete):
- M22-1: skill-native Scanner/Monitor baseline (`market.quote`, `account.orders`, `order.status`) + offline demo
- M22-2: Monitor order lifecycle mapping (`working/partial_fill/filled/cancelled/rejected`) with progress/terminal flags
- M22-3: skill timeout/error fallback quality gates with operator-visible fallback reasons
- M22-4: shared skill DTO contract adapter (`m22.skill.v1`) for Scanner/Monitor
- M22-5: skill hydration node that fetches `market.quote`/`account.orders`/`order.status` into canonical `state["skill_results"]`
- M22-6: graph-spine wiring for skill hydration (before scanner, including retry loop)
- M22-7: operator smoke gate script for hydration/fallback pass-fail checks
- M22-8: opt-in auto connection to `CompositeSkillRunner.from_env()` in hydration node
- M22-9: hydration/fallback metrics integrated into daily metrics report
- M22-10: closeout check script + handover documentation

M23 implementation status (2026-02-17, complete):
- M23-1: runtime resilience state contract scaffold (`state["resilience"]`, `state["circuit"]["strategist"]`) + commander entry normalization
- M23-2: runtime-shared circuit breaker core module (`gate/failure/success`) + transition regression tests
- M23-3: strategist decision path runtime circuit integration (`decide_trade` gate + success/failure state updates)
- M23-4: commander incident counter and cooldown routing policy (`cooldown_wait` short-circuit + runtime error incident registration)
- M23-5: degrade execution policy enforcement (`manual approval required`, `allowlist required`, `degrade notional ratio`)
- M23-6: operator intervention/resume control (`runtime_control=resume`) + intervention runbook/logging
- M23-7: commander resilience ops query CLI (`query_commander_resilience_events.py`) for cooldown/error/intervention visibility
- M23-8: resilience closeout check script and handover (`run_m23_resilience_closeout_check.py`)
- M23-9: commander resilience metrics integrated into daily metrics report (`commander_resilience` block)
- M23-10: final closeout script + M24 handover (`run_m23_closeout_check.py`)

M24 implementation status (2026-02-17, in progress):
- M24-1: strict intent journal state machine + SQLite state/journal store scaffold
- M24-2: ApprovalService integration with SQLite intent state transitions (`approved/executing/executed/failed/rejected`)
- M24-3: duplicate execution claim guard via SQLite CAS (`expected_from_state`) and state-authoritative approval checks
- M24-4: reconciliation tooling between JSONL intent journal and SQLite intent state store (`reconcile_intent_state_store.py`)
- M24-5: real execution preflight hardening with explicit denial reason codes (`check_real_execution_preflight.py`)
- M24-6: guard precedence regression bundle (`run_m24_guard_precedence_check.py`)
- M24-7: intent state/journal ops visibility query CLI with stuck `executing` gate (`query_intent_state_store.py`)
- M24-8: final closeout check and M25 handover (`run_m24_closeout_check.py`)

M25 implementation status (2026-02-17, in progress):
- M25-1: metric schema freeze v1 and validation gate (`check_metrics_schema_v1.py`)
- M25-2: alert policy threshold gate (`check_alert_policy_v1.py`)
- M25-3: alert reporting artifacts and M25 closeout gate (`run_m25_closeout_check.py`)
- M25-4: env-backed alert policy profile + runbook (`ALERT_POLICY_*`, `docs/runtime/alert_policy_runbook.md`)
- M25-5: scheduler-ready ops batch hook with lock/status artifact (`run_m25_ops_batch.py`)
- M25-6: webhook alert channel adapter + batch notification integration (`libs/reporting/alert_notifier.py`)
- M25-7: notification noise control (dedup + rate-limit) with state-backed suppression (`dedup_suppressed`, `rate_limited`)
- M25-8: Slack incoming webhook provider (`slack_webhook`) with shared noise-control policy
- M25-9: bounded notification retry/backoff policy for transient delivery failures (`429`/`5xx`)
- M25-10: notification event log + day-level query CLI for delivery observability

Detailed plan:
- `docs/plan/m20_to_m30_master_plan.md`
- `docs/plan/m31_to_m36_post_golive_plan.md`
