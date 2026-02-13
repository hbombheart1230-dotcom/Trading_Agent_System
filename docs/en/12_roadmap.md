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
