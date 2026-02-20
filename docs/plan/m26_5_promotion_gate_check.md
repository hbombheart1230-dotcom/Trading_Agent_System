# M26-5: Promotion Gate Check

- Date: 2026-02-20
- Goal: convert M26 A/B comparison into deterministic pass/fail promotion decision with explicit thresholds.

## Scope (minimal)

1. Run A/B evaluator and parse winner/recommendation.
2. Apply configurable acceptance thresholds for promotion gate.
3. Return promotion gate result with fail reasons and machine-friendly JSON.

## Implemented

- File: `scripts/run_m26_promotion_gate_check.py`
  - Executes `run_m26_ab_evaluation.py` internally.
  - Applies threshold checks:
    - `--min-delta-total-pnl-proxy`
    - `--min-sortino-proxy`
    - `--max-drawdown-ratio`
  - Enforces winner/recommendation alignment with candidate label:
    - `winner == <b-label>`
    - `recommended_action == promote_<b-label>`
  - Outputs deterministic gate summary and exits with `rc=0` pass / `rc=3` fail.

- File: `tests/test_m26_5_promotion_gate_check.py`
  - Added pass-case test (candidate outperforms baseline and passes thresholds).
  - Added fail-case test (threshold not met).

## Safety Notes

- Promotion gate is analytics-only and does not activate runtime execution.
- This milestone formalizes acceptance policy before any candidate rollout decision.
