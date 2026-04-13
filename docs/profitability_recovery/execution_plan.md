# Profitability Recovery Execution Plan (Start: 2026-04-14)

## Goal
- Diagnose loss structurally
- Close lifecycle (entry → hold → exit → execution → report)
- Improve hold/exit observability
- Establish intraday vs off-hours rules

---

## Day 1 (2026-04-14)

### Pre-market
- Verify latest patches deployed
- Run validation scripts
- Confirm logging fields present

### Intraday (OBSERVE ONLY)
Focus:
- lifecycle completeness
- holding evidence accumulation
- execution field capture

Checkpoints:
- report skipped count
- linkage missing
- hold > 1h trades
- execution missing fields

Allowed changes:
- logging / observability
- linkage bug fix
- execution field capture

Forbidden:
- strategy logic changes
- thresholds / guards

### Post-market
Tasks:
- Add failure classification
- Improve lifecycle closure
- Add execution surface fields
- Add validation scripts

---

## Day 2 (2026-04-15)

### Pre-market
- Confirm all patches applied
- Run checks

### Intraday
Validate:
- lifecycle fully linked
- holding snapshots exist
- exit reasoning visible

### Post-market
- Implement hold/exit analysis
- Add scorecard

---

## Codex Rules
- No strategy logic changes
- Only observability improvements
- All changes additive

