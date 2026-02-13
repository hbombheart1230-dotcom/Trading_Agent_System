# Trading Agent System

## Enterprise Architecture Overview (M15+)

Generated: 2026-02-13 03:02:20

------------------------------------------------------------------------

# 1. Vision

Trading Agent System is a LangGraph-oriented, multi-agent automated
trading system designed with **enterprise-grade safety, governance, and
extensibility**.

Core philosophy:

-   Agents decide. They never execute.
-   Execution is always gated.
-   Guards override approvals.
-   DTO contracts are stable.
-   Every run is traceable.

------------------------------------------------------------------------

# 2. System at a Glance

    Strategist → Scanner → Monitor → OrderIntent
                    ↓
               Supervisor (Approval)
                    ↓
              AgentExecutor
                    ↓
            Execution Layer (Guards)
                    ↓
               Broker (Mock/Real)
                    ↓
            EventLog / Reporter

Key separation: - Decision Layer (Agent) - Approval Layer (Policy) -
Execution Layer (Guarded Action) - Observability Layer (Audit/Trace)

------------------------------------------------------------------------

# 3. Agent Layer Summary

  Agent        Responsibility
  ------------ -----------------------------
  Commander    Orchestrates full run cycle
  Strategist   Builds trade plan
  Scanner      Data + feature extraction
  Monitor      Emits OrderIntent only
  Supervisor   Risk validation + approval
  Executor     Executes approved intents
  Reporter     Post-run analysis

------------------------------------------------------------------------

# 4. Execution & Guard Model

Execution only occurs when:

-   APPROVAL_MODE permits
-   EXECUTION_ENABLED = true
-   Real mode explicitly allowed
-   Symbol is allowlisted
-   Max qty/notional limits respected
-   Intent not already executed

Guard priority overrides approval.

------------------------------------------------------------------------

# 5. Intent Lifecycle

    created → pending_approval → approved → executing → executed/failed → settled

Idempotency enforced via `intent_id`.

------------------------------------------------------------------------

# 6. Contracts & DTO Stability

Core contracts:

-   OrderIntent
-   SupervisorDecision
-   AccountSnapshot
-   MarketSnapshot
-   OrderResult

Rules:

-   Required fields never removed
-   Additive changes only
-   Breaking changes require versioning

------------------------------------------------------------------------

# 7. Observability

Every run shares a `run_id`.

Event log structure (JSONL):

-   ts
-   run_id
-   stage
-   event
-   payload

Real executions are explicitly tagged.

------------------------------------------------------------------------

# 8. Security & Governance

-   .env never committed
-   Real execution default disabled
-   Two-person review recommended for real enable
-   Large orders require manual oversight

------------------------------------------------------------------------

# 9. Deployment Model

Phase 1: Script-based execution\
Phase 2: Container + scheduler\
Phase 3: Full LangGraph orchestration

------------------------------------------------------------------------

# 10. Testing Coverage (M15)

-   mock/manual/auto modes
-   real mode guard
-   max qty / max notional guard
-   legacy AUTO_APPROVE compatibility
-   manual approval flow reproducibility

------------------------------------------------------------------------

# 11. Roadmap

M16: Formal approve(intent_id) API\
M17: Single-source Settings model\
M18: LangGraph full orchestration\
M19+: Metrics dashboard + alerting

------------------------------------------------------------------------

# Enterprise Guarantee

This architecture ensures:

-   Safety before profit
-   Deterministic risk boundaries
-   Auditable execution chain
-   Scalable agent intelligence
