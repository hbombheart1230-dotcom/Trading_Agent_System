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
