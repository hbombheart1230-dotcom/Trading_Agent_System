# 8. Observability

## 8.1 Goals
- every run is traceable via run_id
- approval/guard reasoning is recorded
- incidents can be diagnosed quickly (where and why)

## 8.2 Event Log (JSONL)
Example fields:
- ts, run_id, stage, event(start/end/error), payload

payload should include:
- intent_id
- guard decision (allowed/blocked + reason)
- approval decision
- order_id (if available)

## 8.3 Metrics (Recommended)
- intents_created_total
- intents_approved_total
- intents_blocked_total (by guard_reason)
- execution_latency_seconds
- api_error_total (by api_id)
- strategist_llm.success_rate
- strategist_llm.latency_ms
- strategist_llm.attempts
- strategist_llm.error_type_total

## 8.4 Audit
- tag real executions explicitly
- record config/env changes where possible
