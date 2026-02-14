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

Detailed plan:
- `docs/plan/m20_to_m30_master_plan.md`
