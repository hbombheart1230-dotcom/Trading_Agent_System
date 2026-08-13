# Memory Integrity Correction - 2026-08-13

## Scope

This correction changes memory integrity and observability only. It does not add a new trading tactic, alter Scanner ranking, or change Monitor entry/exit formulas.

## Confirmed Defects

1. Selected-symbol contamination
   - A Stage-2 strategist refresh could target one symbol while `selected_symbol_memory` still described a previously selected symbol.
   - The stale symbol memory could be presented as cautionary context and tighten the current candidate.

2. Contradictory daily strategy memory
   - Sparse daily samples could place the same playbook in both `best_playbooks` and `worst_playbooks`.
   - Single observations could become directional guidance.

3. Empty-day freshness distortion
   - No-trade daily artifacts could crowd evidence-bearing days out of weekly/monthly windows.
   - A stale daily artifact could appear to be the current directional authority.

4. Weak decision linkage
   - Memory visibility was recorded, but symbol consistency and the Stage-2 decision effect were not explicit enough for outcome attribution.

## Fixed Invariants

### Symbol Memory

- Resolve the current expected symbol from the freshest Commander/refresh context.
- Apply symbol memory only when `expected_symbol == memory_symbol`.
- On mismatch:
  - `status = mismatch`
  - `active = false`
  - `override_eligible = false`
  - `override_gate_reason = symbol_memory_mismatch`
- Persist target, memory symbol, consistency, and mismatch-block status in `memory_usage_trace`.

### Strategy Memory

- A playbook needs at least two observations before entering a directional best/worst bucket.
- Best requires non-negative average return and win rate at least 50%.
- Worst requires negative average return or win rate at most 40%.
- Best and worst buckets are mutually exclusive.
- Weekly/monthly windows count evidence-bearing days, not empty artifact directories.
- Daily fallback older than seven calendar days remains audit evidence but loses directional authority.

### Usage Trace

The strategist artifact now records:

- target symbol and memory symbol
- symbol consistency and mismatch gate
- LLM-reported memory effect and reason
- whether entry confidence was tightened
- Q9 decision ID when available
- strategist run ID

This is the minimum linkage needed to compare memory-informed decisions against later outcomes without inferring causality from prompt presence alone.

## Validation

Regression coverage includes:

- cross-symbol memory rejection
- sparse best/worst exclusion and bucket disjointness
- no-trade day exclusion from memory windows
- fallback freshness metadata
- memory effect and decision-link trace

## Operating Rule

Do not judge memory effectiveness from `memory_used=true` alone. A valid effectiveness sample requires:

1. symbol consistency
2. usable evidence age and sample count
3. explicit decision effect
4. a linked forward/trade outcome
