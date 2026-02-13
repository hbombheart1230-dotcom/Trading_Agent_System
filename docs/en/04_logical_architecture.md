# 4. Logical Architecture

## 4.1 Layers
1) Agent Layer: decisions and intent generation (no side-effects)
2) Approval Layer: Supervisor decisions
3) Execution Layer: guarded calls, broker routing, idempotency
4) Contract Layer: DTO/IO contracts, API catalog
5) Observability Layer: events, metrics, audits

## 4.2 Component Responsibilities

### Agent Layer
- Strategist: define candidates/scenarios/constraints
- Scanner: quantify and rank candidates via data/skills
- Monitor: watch and emit OrderIntents (no execution)
- Reporter: replay logs, summarize and recommend improvements

### Approval Layer (Supervisor)
- policy validation: max qty/notional, allowlist, daily loss, etc.
- approval mode: auto/manual
- modify approval: adjust qty/price/type

### Execution Layer
- guard evaluation
- broker routing (mock/real)
- idempotent execute: avoid duplicates per intent_id
- persist execution results to logs

## 4.3 Contract-centric Data Flow
- Raw API responses stay inside skills
- Agents/Reporter consume DTOs only
- Breaking contract changes require versioning and migration
