# 5. 런타임 플로우 (시퀀스/상태 머신)

## 5.1 한 사이클(run) 시퀀스 (텍스트 시퀀스 다이어그램)

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

## 5.2 Intent 상태 머신 (텍스트 다이어그램)

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

규칙: 동일 intent_id는 (executing) 중복 진입 금지.
