# 2. Principles and Non-Negotiable Rules

## 2.1 Non-negotiables
1) The Monitor must never place orders (structurally prohibited).
2) The Execution Layer must never execute without approval.
3) Guards override approvals (approved but guarded == blocked).
4) DTO/IO contracts must not introduce breaking changes.
5) Logging is observational only (must not alter control flow).

## 2.2 Design Principles
- Single Source of Truth: Settings/env/config are read through one canonical path.
- Determinism where possible: Risk/Guard logic must be deterministic.
- Idempotency: the same `intent_id` must not execute twice.
- Small surface area: keep approval/execution APIs minimal and stable.
- Safe defaults: the default stance is “do not execute”.

## 2.3 Mistake-proofing Guidelines
- Real mode is blocked by default unless explicitly allowed.
- If `EXECUTION_ENABLED=false`, execution is always blocked.
- Define a strict operational policy for allowlists and limits.
