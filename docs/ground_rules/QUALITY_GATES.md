# QUALITY_GATES.md
> Trading_Agent_System — Quality Gates / CI-like Checklist (M20 Prep)

This file defines the minimum “CI gates” for changes (human or Codex).

---

## 1) Mandatory Gates (Every Change)

### A. Tests
- Run: `python -m pytest -q`
- Tests must be deterministic and reproducible.
- If a test fails, fix it **before** adding new changes.

### B. Safety Rules (Audit Checklist)
Confirm:
- Monitor does not execute (no broker calls).
- Execution never occurs without approval.
- Guards override approvals.
- Default stance remains “do not execute”.

### C. Contracts
- No breaking changes to IO/DTO required fields.
- Any schema evolution is additive or versioned.

### D. Secrets / Compliance
- `.env` is gitignored and never modified.
- No secrets in logs / CI output.
- File permissions policy (local) respected.

### E. Documentation
- For every meaningful behavior/config/contract change, update relevant `docs/` files in the same task.
- At minimum, update one implementation-facing note under `docs/plan/` and one canonical doc if behavior changed.

---

## 2) Required Regression Scenarios (M15 baseline)

Minimum coverage must include:
- mock/manual/auto + execution enable/disable
- real mode guard (ALLOW_REAL_EXECUTION, allowlist)
- max qty / max notional guard
- legacy AUTO_APPROVE true/false compatibility
- manual approval path output/flow

---

## 3) Review Output Requirements (for Codex/PR)

Every completed task must produce:
- Changed file list
- Rationale (why these changes)
- Risk notes (what could break)
- How tests were validated (command + result)
- Documentation delta (which `docs/` files were updated and why)
- Any follow-up tasks (if postponed)

---

## 4) “Stop Conditions” (Do Not Merge)

Stop and redesign if:
- Any Non-negotiable is violated.
- Guard precedence changes unintentionally.
- Contracts break without versioning.
- Tests become flaky or rely on wall-clock randomness.
