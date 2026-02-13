# 1. Vision and System Overview

## 1.1 Goals
The Trading Agent System is an **agentic automated trading system** designed to satisfy:

- **Safety first**: real trading must pass “approval + guards”.
- **Strict separation**: decision-making (Agent Layer) is isolated from execution (Execution Layer).
- **Reproducibility**: every decision and action is traceable by `run_id`.
- **Extensibility**: naturally expandable toward LangGraph orchestration.
- **Operability**: operators can stop/allow/audit the system at any time.

## 1.2 Core Components
- Commander: orchestrates a run cycle
- Strategist: proposes candidates/scenarios/constraints
- Scanner: data collection/feature computation/ranking
- Monitor: watches signals and emits OrderIntent (must NOT execute)
- Supervisor: risk/policy validation → approve/reject/modify
- Executor: executes only approved intents (calls Execution Layer)
- Reporter: log-based reports and post-mortems

## 1.3 What “Enterprise” Means Here
“Enterprise” includes:
- operational standards (runbooks, incident response, rollback, alerts)
- security standards (secrets, access control, audit)
- quality standards (regression, contract stability, test coverage)
- change management standards (migration, compatibility, versioning)

## 1.4 At-a-Glance Diagram (Text)

[User/Operator]
      |
      v
+-------------------+
| Commander (Cycle) |
+-------------------+
      |
      v
+-----------+    +---------+    +---------+
| Strategist| -> | Scanner | -> | Monitor |
+-----------+    +---------+    +---------+
      |                               |
      |                               v
      |                         +-------------+
      |                         | OrderIntent |
      |                         +-------------+
      |                               |
      v                               v
+-------------------+        +-------------------+
| Supervisor (Gate) | -----> | AgentExecutor     |
+-------------------+        +-------------------+
                                      |
                                      v
                           +-----------------------+
                           | Execution Layer       |
                           | (Guards + Broker API) |
                           +-----------------------+
                                      |
                                      v
                            +---------------------+
                            | EventLog / Reports  |
                            +---------------------+

Key idea: Agents go only as far as “intent”. Execution happens only behind guards.
