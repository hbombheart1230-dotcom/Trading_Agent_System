# 5. Runtime Flow (Sequence / State Machine)

## 5.1 Run Cycle Sequence (Text Sequence Diagram)

Operator -> Commander: start_run(goal, config)
Commander -> Strategist: build_trade_plan()
Strategist -> Commander: TradePlan
Commander -> Scanner: scan(plan)
Scanner -> Commander: ScanResult
Commander -> Monitor: monitor(scan_result)
Monitor -> Commander: OrderIntent(s)
Commander -> Supervisor: decide(intent)
Supervisor -> Commander: SupervisorDecision (approve/reject/modify)
Commander -> AgentExecutor: handle(decision, intent)
AgentExecutor -> ExecutionLayer: execute(intent) [only if approved]
ExecutionLayer -> Broker(Mock/Real): place/cancel/status
Broker -> ExecutionLayer: OrderResult/OrderStatus
ExecutionLayer -> EventLog: append events
Commander -> Reporter: report(run_id)
Reporter -> Operator: summary

## 5.2 Intent State Machine (Text Diagram)

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

Rule: the same intent_id must not re-enter (executing) twice.
