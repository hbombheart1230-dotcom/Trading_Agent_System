# M26-4: A/B Evaluation Scaffold

- Date: 2026-02-20
- Goal: compare two strategy candidates (A/B) using M26 scorecard outputs and produce promotion guidance.

## Scope (minimal)

1. Execute scorecard for A/B dataset inputs.
2. Compare key metrics with deterministic point rules.
3. Produce conservative promotion recommendation.

## Implemented

- File: `scripts/run_m26_ab_evaluation.py`
  - Runs `run_m26_scorecard.py` for:
    - `--a-dataset-root`
    - `--b-dataset-root`
    - optional `--day`
  - Compares metrics:
    - `total_pnl_proxy` (higher better)
    - `risk_adjusted.sortino_proxy` (higher better)
    - `risk_adjusted.sharpe_proxy` (higher better)
    - `drawdown.max_drawdown_ratio` (lower better)
    - `win_rate` (higher better)
  - Produces:
    - per-metric winner + delta
    - points summary
    - overall winner
    - `promotion_gate.recommended_action` (`promote_<label>` / `no_promote_<label>` / `hold`)

- File: `tests/test_m26_4_ab_evaluation.py`
  - Added pass-case test where candidate(B) is promoted over baseline(A).
  - Added fail-case test for invalid/missing B dataset.

## Safety Notes

- A/B evaluator is analytics-only and does not modify runtime execution behavior.
- Promotion recommendation is conservative and should still pass operator review gates.
