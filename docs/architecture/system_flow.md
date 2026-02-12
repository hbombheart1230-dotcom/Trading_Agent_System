# Trading Agent System – System Flow

## High-level Flow

1. Market Reader
2. Portfolio Reader
3. Strategist (Rule / LLM)
4. Decision Packet
5. Risk Supervisor
6. Executor (mock / live)
7. Event Logger
8. Reports

## Pipeline Role

Pipelines define **when** and **in what order** nodes run.
Nodes define **what** happens.

## libs vs graphs

- libs/: pure logic, reusable, testable
- graphs/nodes: glue layer (state in/out)
- graphs/pipelines: orchestration scripts
