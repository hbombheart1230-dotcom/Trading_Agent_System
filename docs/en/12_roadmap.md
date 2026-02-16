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

M22 implementation status (2026-02-15, in progress):
- M22-1: skill-native Scanner/Monitor baseline (`market.quote`, `account.orders`, `order.status`) + offline demo
- M22-2: Monitor order lifecycle mapping (`working/partial_fill/filled/cancelled/rejected`) with progress/terminal flags
- M22-3: skill timeout/error fallback quality gates with operator-visible fallback reasons
- M22-4: shared skill DTO contract adapter (`m22.skill.v1`) for Scanner/Monitor
- M22-5: skill hydration node that fetches `market.quote`/`account.orders`/`order.status` into canonical `state["skill_results"]`
- M22-6: graph-spine wiring for skill hydration (before scanner, including retry loop)
- M22-7: operator smoke gate script for hydration/fallback pass-fail checks
- M22-8: opt-in auto connection to `CompositeSkillRunner.from_env()` in hydration node
- M22-9: hydration/fallback metrics integrated into daily metrics report

Detailed plan:
- `docs/plan/m20_to_m30_master_plan.md`
