# AGENT_RULES.md
> Trading_Agent_System — Agent Rules / Non‑Negotiables (M20 Prep)

This file is the **hard guardrail** for any human or AI (Codex) changes.
If a proposed change violates any item below, **STOP** and redesign.

---

## 1) Core Non‑Negotiables (Must Hold Always)

1. **Monitor must never place orders** (structurally prohibited).
2. **Execution Layer must never execute without approval**.
3. **Guards override approvals** (approved but guarded == blocked).
4. **DTO/IO contracts must not introduce breaking changes** (use versioning).
5. **Logging/observability is observational only** (must not alter control flow).
6. **Default stance is “do not execute”** (safe defaults).

---

## 2) Role Boundaries (Who Does What)

### Commander (지휘관) — Orchestrator
- Owns the **run-cycle orchestration** (who to call next, when to pause/stop).
- Routes outputs between agents (plan → scan → monitor → approve → execute).
- Handles abnormal events (API failure, guard blocks, retries/cancel).
- Triggers approval → execution chain via Supervisor + AgentExecutor.
- **Does NOT**:
  - select symbols directly
  - compute indicators/features
  - place orders

### Strategist (전략가)
- Chooses candidates (typically 3–5) and scenarios (entry/add/stop/take-profit).
- Decides what signals/news/features to consult (but does not execute).

### Scanner (스캐너)
- Fetches data via skills with accuracy.
- Computes features and returns ranked results + gaps/uncertainty.

### Monitor (모니터)
- Watches the chosen primary symbol(s) (initially 1).
- Emits **ActionProposal / OrderIntent** only.
- **Never executes** or calls broker APIs.

### Supervisor (감독관)
- Owns risk limits and policy.
- Validates OrderIntent and **approves / rejects / modifies**.
- Can pause/stop the system.

### AgentExecutor (에이전트 수행자) — Bridge
- Translates SupervisorDecision + OrderIntent into an execution request.
- Must obey all guards and idempotency rules.

### Execution Layer (실행 계층)
- Guard evaluation (EXECUTION_ENABLED, real-mode allow, allowlist, limits, idempotency).
- Broker routing (mock/real).
- Side-effect boundary (only place/cancel/status).

### Reporter (리포터)
- Reads EventLog and produces reports / improvement suggestions.
- No control authority; does not change runtime decisions.

---

## 3) Guard Precedence (Must Preserve Order)

1) EXECUTION_ENABLED == false → always block  
2) KIWOOM_MODE == real AND ALLOW_REAL_EXECUTION != true → block  
3) SYMBOL_ALLOWLIST mismatch → block  
4) MAX_QTY exceeded → block  
5) MAX_NOTIONAL exceeded → block  
6) Idempotency (intent_id already executed) → block  

**Rule:** the same `intent_id` must not execute twice.

---

## 4) Contract Stability (DTO/IO)

- Required fields must never be removed.
- Additive changes only (optional/defaults).
- Semantic changes prohibited → add new field instead.
- Versioning policy: keep `dto_version="v1"`, introduce `v2` in parallel for breaking changes.

---

## 5) Change Discipline (How We Work)

- Prefer **small PR-sized changes** (one goal, bounded files).
- Update documentation in `docs/` for every meaningful behavior/config/contract change in the same task.
- Run tests locally before “done”.
- Never print secrets; never commit `.env`.
- If you must touch frozen areas (Execution/Guards/Contracts), explain why and add regression tests.
