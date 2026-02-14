# M20 — LangGraph Orchestration Spec (Commander-centric)

This document defines how existing agents map into **LangGraph nodes** while preserving
the M15 architecture: Agents produce intents; Execution is gated by approval + guards.

---

## 1) Goals
- Introduce a formal graph orchestration layer without changing core business behavior.
- Keep IO/DTO contracts stable (OrderIntent, SupervisorDecision, etc.).
- Preserve guard precedence and “do not execute” defaults.

---

## 2) State Model (Graph State)
Recommended minimal `GraphState` (conceptual):

- run_id: str
- config: RunConfig / Settings snapshot
- trade_plan: TradePlan | None
- scan_result: ScanResult | None
- action_proposal: ActionProposal | None
- intent: OrderIntent | None
- decision: SupervisorDecision | None
- execution_result: OrderResult | None
- errors: list[ErrorEvent] (optional)
- status: enum (running/paused/stopped/completed)

**Rule:** `intent_id` must be idempotent. The same intent cannot reach execution twice.

---

## 3) Node Map (Role → LangGraph Node)

### Node: commander_router
**Owner:** Commander  
**Input:** GraphState  
**Output:** GraphState + next step label  
**Responsibility:** choose the next node based on state/status (e.g., need plan? scan? monitor? approve? execute? report?).

### Node: strategist_build_plan
**Owner:** Strategist  
**Input:** GraphState(config, goal, recent_context)  
**Output:** GraphState(trade_plan=TradePlan)

### Node: scanner_rank_universe
**Owner:** Scanner  
**Input:** GraphState(trade_plan)  
**Output:** GraphState(scan_result=ScanResult)

### Node: monitor_watch_and_intent
**Owner:** Monitor  
**Input:** GraphState(scan_result)  
**Output:** GraphState(intent=OrderIntent or action_proposal)

**Hard rule:** no execution side-effects. Emit intent only.

### Node: supervisor_decide
**Owner:** Supervisor  
**Input:** GraphState(intent, config)  
**Output:** GraphState(decision=SupervisorDecision)

### Node: agent_executor_handle
**Owner:** AgentExecutor  
**Input:** GraphState(intent, decision)  
**Output:** GraphState(execution_request=...) OR GraphState(noop)  

This node must respect: approved only, and still pass execution guards.

### Node: execution_layer_execute
**Owner:** Execution Layer  
**Input:** execution_request + Settings  
**Output:** GraphState(execution_result=OrderResult)

**Hard rule:** execution happens only here, behind guards.

### Node: reporter_summarize
**Owner:** Reporter  
**Input:** GraphState(run_id, logs)  
**Output:** GraphState(report=...)

---

## 4) Transitions (High-level)
Typical cycle:

commander_router
 → strategist_build_plan
 → scanner_rank_universe
 → monitor_watch_and_intent
 → supervisor_decide
 → agent_executor_handle
 → (if approved) execution_layer_execute
 → reporter_summarize
 → commander_router (loop or stop)

---

## 5) Retry / Cancellation / Pause Policy
- Commander owns pause/stop decisions.
- Retry is allowed only for **safe, idempotent** operations (e.g., transient API read failures).
- Never retry an execution that might place duplicate orders unless idempotency guarantees are verified.
- Manual approval mode must remain reproducible (M16 approve API later).

---

## 6) Implementation Guardrails
- Freeze DTO/IO contracts during M20 scaffolding.
- Keep Execution/Guards unchanged unless explicitly part of a later milestone.
- All changes must pass `python -m pytest -q`.

