# 2026-05-21 Close Review And Q8 Findings

## Day Result

Source: `reports/operator_summary/daily/2026-05-21/daily_summary.json`

- Trades: 8
- Closed trades: 6
- Wins/Losses: 3 / 3
- Win rate: 50.00%
- Average return: -0.4078%
- Average hold: 1,759.5 sec
- Return basis: truth-surface net

The day improved versus the weekly baseline, but the average return stayed
negative because two 034220 fixed-stop losses dominated the PnL.

## Pattern Read

Daily summary:

- Strategist tactical:
  - `opening_range_breakout`: 6 trades, win 60.0%, avg -0.35%
  - `opening_gap_momentum`: 2 trades, win 0.0%, avg -0.72%
- Quant tactic:
  - `defensive_observe`: 3 trades, win 66.7%, avg +0.65%
  - `opening_range_breakout`: 3 trades, win 0.0%, avg -3.11%
  - `opening_gap_momentum`: 2 trades, win 100.0%, avg +1.82%
- Quant exit quality:
  - `hard_exit`: 3 trades, win 0.0%, avg -2.31%
  - `exit_aligned`: 3 trades, win 100.0%, avg +1.50%

Read:

- The issue was not simple trade frequency.
- `opening_range_breakout` plus hard/fixed-stop exits was the main loss
  cluster.
- `exit_aligned` exits worked today.
- `hard_exit` stayed necessary as risk control, but the entry cluster that led
  into hard exits needs review.

## Post-Exit Shadow Read

Post-exit recap observed all six closed trades.

- 024840: best `+5m`, +60m 0.00%
- 012330: best `+60m`, +60m +4.85%
- 034220_01: best `+30m`, +60m +0.13%
- 006345: best `+5m`, +60m +1.77%
- 233740: best `+5m`, +60m -0.76%
- 034220_02: best `+5m`, +60m -0.27%, EOD -0.27%

Read:

- One trade, 012330, strongly supports longer hold observation.
- Two trades, 233740 and 034220_02, weakened after exit.
- This is not enough evidence to unlock long-horizon holding globally.
- The right next split is by tactic ID, hard-exit state, and cost-floor state,
  not by symbol name.

## Q1-Q7 Validation

What worked:

- Q7 summary surface exists in trade summary input.
- `quant_tactic.tactic_id` exists on closed trade summary inputs.
- `exit_quant_decision` exists and separates `hard_exit` from `exit_aligned`.
- Post-exit shadow recap now refreshes individual trade summaries and daily
  recap.
- Symbol metadata now renders 006345 as `대원전선우` with themes
  `전선`, `전력설비`, `구리`.

Mismatch:

- `entry_quant_decision` is empty on all six closed trade summary inputs.
- `tactic_suitability` is empty on all six closed trade summary inputs.
- Scanner chart-fit score was not available in the summary input extraction
  path used for this review.

Impact:

- Q6 is not fully reviewable at trade-summary level.
- We can evaluate exit quality and post-exit behavior today.
- We cannot yet reliably evaluate whether Q6 entry blockers would have vetoed
  the bad entries.

## Decision

Do not promote another behavior rule tonight.

Priority before behavior promotion:

1. Fix Q8 artifact integrity for entry-side quant fields.
2. Make executed trade summaries carry:
   - `entry_quant_decision`
   - `tactic_suitability`
   - cost floor state
   - scanner chart-fit score
   - commander override reason
3. Re-run one more live day or at least tomorrow morning sample before
   promoting runner-up or long-horizon behavior.

Candidate next behavior after integrity fix:

- Degrade or restrict `opening_range_breakout` entries when the setup is
  repeatedly leading to hard exits.
- Keep `exit_aligned` logic as-is.
- Keep post-exit shadow observation-only.

## Q8 Artifact Integrity Patch

Completed after the close review.

Code changes:

- `libs/reporting/quant_tactic_report.py`
  - Recovers the executed symbol from the report/fact payload.
  - Finds the selected scanner candidate row recursively by symbol.
  - Uses selected candidate `quant_factor_snapshot` as a fallback.
  - Rebuilds missing `entry_quant_decision` from
    `entry_execution_visibility`, monitor state, and scanner candidate data.
  - Recomputes missing `tactic_suitability` from the selected candidate.
  - Adds `scanner_chart_fit` to the quant tactic report surface.
- `libs/runtime/quant/decision.py`
  - Derives `cost_floor_state` from the cost filter when the explicit factor
    is missing.
- `tests/test_quant_tactic_report.py`
  - Adds coverage that proves trade summary diagnostics can be recovered from
    execution visibility plus scanner evidence.

Regenerated artifacts:

- `scripts/run_post_exit_shadow_recap.py --day 2026-05-21 --json`
- `scripts/run_operator_daily_summary.py --day 2026-05-21 --json`
- `scripts/generate_daily_report.py` with alternate day-cache directory after
  the default cache file was locked by another process.

Validation:

- Targeted regression passed: 23 tests.
- All six closed 2026-05-21 trade summary inputs now include:
  - `entry_quant_decision`
  - `cost_floor_state`
  - `tactic_suitability`
  - scanner chart-fit score

Recovered entry-side diagnostics:

| Trade | Tactic | Entry decision | Cost floor | Suitability | Chart score |
| --- | --- | --- | --- | --- | --- |
| TRD_20260521_024840_01 | defensive_observe | entry_ready | met | weak | 0.1321 |
| TRD_20260521_012330_02 | defensive_observe | entry_ready | met | watch | 0.4488 |
| TRD_20260521_034220_01 | opening_range_breakout | entry_ready | met | weak | 0.4769 |
| TRD_20260521_006345_01 | opening_gap_momentum | entry_ready | met | weak | 0.4000 |
| TRD_20260521_233740_01 | opening_range_breakout | block_recommended | not_met | watch | 0.5600 |
| TRD_20260521_034220_02 | opening_range_breakout | entry_ready | met | weak | 0.1892 |

Patch read:

- `233740` is the clearest Q8 finding. It now shows
  `block_recommended`, `cost_floor_state=not_met`, and blockers including
  `cost_edge_fail` and `volume_confirmation_missing`.
- Weak suitability alone should not become a hard veto yet. Some profitable
  trades, including `024840` and `006345`, also recovered as weak suitability.
- `034220_02` deserves review because chart-fit was very weak at 0.1892 while
  the reconstructed entry decision was still `entry_ready`.

Next behavior-promotion candidate:

- Promote entry-side cost/volume blockers first, not raw suitability tier.
- Keep tactic suitability and chart-fit as diagnostics until another live
  sample confirms which thresholds separate losses from wins.
