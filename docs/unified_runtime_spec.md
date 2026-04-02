# Unified Runtime Spec (Trading Agent System)

## 1. System Overview
- Multi-agent trading system
- Agents decide, never execute
- Execution always gated by Supervisor + Guards
- All decisions traceable via run_id

Agents:
Commander → Strategist → Scanner → Monitor → Supervisor → Executor → Reporter


## 2. Runtime Flow
Commander orchestrates one cycle:

Strategist → Scanner → Monitor → Supervisor → Executor → Reporter

Monitor emits OrderIntent only (never executes).


## 3. Data Flow (Source of Truth)

1. Event Log (raw evidence)
2. Canonical Artifacts (per-agent decision outputs)
3. Trade Artifacts (lifecycle aggregation)
4. Reports / UI (LLM narrative layer)

Reader priority:
canonical > trade artifact > event log


## 4. Contracts

### 4.1 IO Contracts
- OrderIntent (Monitor → Supervisor)
- SupervisorDecision (Supervisor → Executor)

### 4.2 DTO
- AccountSnapshot
- MarketSnapshot
- CandleSeries
- UniverseResult
- OrderResult / OrderStatus

Rules:
- Required fields never removed
- Additive changes only
- raw/extra for extension


## 5. Agents

### Commander
- Orchestrates cycle
- Routing only

### Strategist
- Market context + policy generation
- Owns strategy_policy

### Scanner
- Candidate selection & ranking

### Monitor
- Entry/Exit 판단
- OrderIntent 생성

### Supervisor
- Approval / Risk check

### Executor
- 실제 주문 실행 (approved only)

### Reporter
- 사후 분석


## 6. Skill Layer

Raw API → Composite Skill → DTO → Agent

Agents never see raw API.


## 7. LLM Layer

Used for:
- Strategist
- Trade Report
- Operator Brief
- Daily Report

Rule:
LLM = narrative only (not source of truth)


## 8. Observability

- events.jsonl
- decision_trace
- evidence_ledger

All runs traceable via run_id


## 9. Execution / Guard

Execution requires:
- approval
- execution_enabled
- guard pass

Guards override approval


## 10. Principles

- Monitor must not execute
- Execution must not bypass approval
- Guards override everything
- Deterministic risk logic
- Safe defaults (do not execute)
