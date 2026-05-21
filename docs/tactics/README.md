# Trading Tactics Baseline

This folder is the operator-facing baseline for tactical trading changes.

Use it before changing runtime strategy, scanner selection, monitor entry/exit,
cache routing, or reporting rules. Daily patch notes record what changed; this
folder records what the system is trying to optimize and which rules are
allowed to change behavior.

## Files

- `tactical_operating_baseline.md`: current tactical policy, guardrails,
  open problems, and patch queue.
- `quant_tactic_engine_plan.md`: modular plan for adding a quant-style tactic
  layer without replacing the current commander, strategist, scanner, monitor,
  execution, reporting, and memory flow.
- `quant_tactic_engine_phase_plan.md`: phase and slice plan for implementing
  the quant tactic layer with modularity and minimal runtime disruption.

## Update Rule

Every tactical patch should update `tactical_operating_baseline.md` when it:

- changes entry eligibility
- changes exit timing
- changes strategist/scanner/monitor authority
- changes cache routing that affects LLM refresh frequency
- changes carry or horizon behavior
- promotes an observation-only signal into behavior

Do not use this folder for broad refactor notes. Keep refactor progress in
`docs/daily_patch` or `docs/dev`.
