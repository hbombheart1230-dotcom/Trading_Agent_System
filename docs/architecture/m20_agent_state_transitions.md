# Agent Runtime — State Transitions & Diagrams (M20)

This document describes the runtime flow as a text diagram suitable for docs and review.

---

## 1) Run Cycle (Sequence)

Operator -> Commander: start_run(goal, config)
Commander -> Strategist: build_trade_plan()
Strategist -> Commander: TradePlan
Commander -> Scanner: scan(plan)
Scanner -> Commander: ScanResult
Commander -> Monitor: monitor(scan_result)
Monitor -> Commander: OrderIntent(s) / ActionProposal
Commander -> Supervisor: decide(intent)
Supervisor -> Commander: SupervisorDecision (approve/reject/modify)
Commander -> AgentExecutor: handle(decision, intent)
AgentExecutor -> ExecutionLayer: execute(intent) [only if approved AND not guarded]
ExecutionLayer -> Broker(Mock/Real): place/cancel/status
Broker -> ExecutionLayer: OrderResult/OrderStatus
ExecutionLayer -> EventLog: append events
Commander -> Reporter: report(run_id)
Reporter -> Operator: summary

---

## 2) Intent Lifecycle (State Machine)

(created)
   |
   v
(pending_approval) --reject--> (rejected)
   |
   +--approve--> (approved)
                   |
                   v
               (executing)
                   |
         +---------+----------+
         |                    |
         v                    v
     (executed)            (failed)
         |
         v
 (settled/closed)  [optional]

Rules:
- The same intent_id must not re-enter (executing) twice (idempotency).
- Guards can block an approved intent at any time (approved but guarded == blocked).

---

## 3) Commander Routing (Decision Diagram)

IF status == paused -> wait_for_operator
ELIF no trade_plan -> strategist_build_plan
ELIF no scan_result -> scanner_rank_universe
ELIF no intent -> monitor_watch_and_intent
ELIF intent exists AND no decision -> supervisor_decide
ELIF decision == reject -> clear intent / continue loop
ELIF decision == approve -> agent_executor_handle
ELIF execution requested -> execution_layer_execute
ELIF execution_result -> reporter_summarize
ELSE -> stop (completed)

---

## 4) Failure / Incident Routing

- Transient read API errors:
  - Commander may retry with bounded attempts + backoff.
- Guard blocks:
  - Record guard_reason in event log and route to Reporter.
  - Commander may pause system if repeated blocks occur.
- Real execution risk:
  - If EXECUTION_ENABLED=false or real-mode not explicitly allowed, execution is blocked.

