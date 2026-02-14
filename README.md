# Trading Agent System

## Enterprise Architecture Overview (M20)

Generated: 2026-02-14 13:29:06

------------------------------------------------------------------------

# 1. Vision

Trading Agent System is a LangGraph-oriented, multi-agent automated trading system designed with enterprise-grade safety, governance, and extensibility.

Core philosophy:

- Agents decide. They never execute directly.
- Execution is always gated.
- Guards override approvals.
- DTO contracts are stable.
- Every run is traceable.
- LLM is advisory only (never execution authority).

------------------------------------------------------------------------

# 2. System at a Glance (7-Agent Model)

    Commander (지휘관)
        ↓
    Strategist (전략가)
        ↓
    Scanner (스캐너)
        ↓
    Monitor (모니터)
        ↓
    Supervisor (감독관)
        ↓
    Executor (수행자)
        ↓
    Broker (Mock/Real)
        ↓
    Reporter (리포터)

Key separation:
- Decision Layer (Commander, Strategist, Scanner, Monitor)
- Approval Layer (Supervisor)
- Execution Layer (Executor + Guards)
- Observability Layer (Reporter + EventLog)

------------------------------------------------------------------------

# 3. Agent Responsibilities

## Commander (지휘관)
- Orchestrates full run cycle
- Decides which agent to call next
- Routes outputs between agents
- Handles abnormal events (guard block, LLM failure, emergency stop)
- Never selects stocks directly
- Never executes trades

## Strategist (전략가)
- Selects candidate symbols (3~5)
- Defines scenarios (entry/add/stop/take-profit)
- May consult LLM for scenario reasoning
- Produces structured intent proposal

## Scanner (스캐너)
- Fetches market/account data via skills
- Computes indicators (volatility, momentum, volume spike, etc.)
- Ranks candidates

## Monitor (모니터)
- Watches selected primary symbol
- Emits ActionProposal / OrderIntent
- Never places orders

## Supervisor (감독관)
- Owns risk limits and policy
- Validates OrderIntent
- Approves / rejects / modifies
- Can pause/stop system

## Executor (수행자)
- Executes approved intents only
- Applies guard precedence
- Ensures idempotency
- Routes to Broker API

## Reporter (리포터)
- Reads EventLog
- Produces daily / trade / system reports
- Summarizes LLM quality and execution metrics

------------------------------------------------------------------------

# 4. Execution & Guard Model

Execution occurs only when:

- APPROVAL_MODE permits
- EXECUTION_ENABLED = true
- Real mode explicitly allowed
- Symbol allowlist satisfied
- Max qty/notional limits respected
- Intent not already executed

Guard priority always overrides approval.

------------------------------------------------------------------------

# 5. Intent Lifecycle

    created → pending_approval → approved → executing → executed/failed → settled

Idempotency enforced via intent_id.

------------------------------------------------------------------------

# 6. LLM Architecture (M20)

Current State:
- OpenRouter integration via OpenAI-compatible adapter
- Provider-agnostic LLM interface
- JSON intent normalization: { "intent": ... }
- Schema validation enforced
- Retry with exponential backoff
- Error-type classification
- LLM telemetry logging (`stage=strategist_llm`)
- Operator smoke and query scripts for LLM telemetry

Implemented Milestones:
- M20-1: strategist smoke + safe fallback
- M20-2: adapter parsing + normalization + retry/telemetry
- M20-3: legacy LLM router compatibility fix
- M20-4: smoke visibility options + event query CLI

Next Steps:
- Circuit breaker + safe fallback mode
- Prompt versioning and contract freeze
- Cost/token tracking
- LangGraph formal state machine orchestration

------------------------------------------------------------------------

# 7. Observability

Every run includes a run_id.

Event log (JSONL):

- ts
- run_id
- stage
- event
- payload
- error_type (if applicable)
- latency_ms (LLM/execution)

LLM telemetry tracked separately from trading logic.

------------------------------------------------------------------------

# 8. Security & Governance

- .env never committed
- Real execution disabled by default
- Two-person review recommended for real mode
- LLM has zero execution authority
- Execution always guarded

------------------------------------------------------------------------

# 9. Deployment Model

Phase 1: Script-based execution  
Phase 2: Container + scheduler  
Phase 3: Full LangGraph orchestration  
Phase 4: Metrics + alerting + circuit breaker  

------------------------------------------------------------------------

# 10. Testing Coverage

- mock/manual/auto modes
- real mode guard enforcement
- max qty / max notional guard
- legacy AUTO_APPROVE compatibility
- manual approval reproducibility
- LLM schema validation tests

------------------------------------------------------------------------

# 11. Roadmap

M20:
- LangGraph orchestration
- Provider-agnostic LLM integration
- Schema validation enforcement
- LLM retry/telemetry and operator tooling

M21:
- Circuit breaker
- Safe fallback mode
- Telemetry dashboard

M22+:
- Cost optimization layer
- Multi-provider LLM routing
- Strategy evaluation framework

------------------------------------------------------------------------

# Enterprise Guarantee

This architecture ensures:

- Safety before profit
- Deterministic risk boundaries
- Auditable execution chain
- Scalable agent intelligence
- Provider-agnostic LLM extensibility
