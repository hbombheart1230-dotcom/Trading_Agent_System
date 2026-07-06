# Post-Q9 Code and Data Audit Matrix

Date: 2026-07-06

Purpose: separate what can already be proven from code, what can be concluded from accumulated artifacts, and what still requires a focused patch or controlled retest. This document is meant to stop circular evaluation and keep the next work package evidence-driven.

## Authority Rule

When artifacts disagree, use this order until a single canonical closeout generator is enforced:

1. Broker truth / lifecycle truth for realized trades.
2. Machine-readable JSON ledger and daily verification artifacts.
3. Markdown summaries generated from those JSON artifacts.
4. LLM narrative text.

Current known mismatch:

- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/daily_ledger.json` records 2026-07-06 +30m commander-minus-baseline alpha as `+0.0689`.
- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/q9_closure_summary_2026-07-06.md` still records the same day as `-0.0021`.
- Treat the JSON ledger and `post_close_verification.json` as authoritative. The markdown closeout needs regeneration or a deterministic drift check.

## Status Legend

- `CONFIRMED`: directly visible in code and supported by artifacts.
- `PARTIAL`: implemented or measured, but not complete enough to support a production policy alone.
- `DATA_ONLY`: supported by historical/Q9 artifacts, but not directly provable from code structure alone.
- `OPEN`: not yet proven; do not make production behavior changes from it.

## Code Findings

| Topic | Status | Evidence | Decision |
| --- | --- | --- | --- |
| Commander is not the primary stock selector | `CONFIRMED` | `libs/runtime/q9_decision_snapshots.py` labels commander scope as `final_approval_or_veto`; `libs/runtime/commander/strategist_cycle.py` runs post-scanner selected-symbol refresh; `libs/runtime/commander/strategist_refresh_decision.py` refreshes tactical context for an already selected symbol. | Stop saying "Commander changed the stock" unless artifacts show actual selected-symbol change. Treat Commander mainly as approval/veto/risk control. |
| Strategist direct stock selection is not proven | `PARTIAL` | Q9 has `strategist_selection.post_strategist_top10` and `selected_symbol`, but post-scanner refresh code is a tactical refresh of the selected symbol, not a clean LLM stock-pick authority. | Interpret B as strategy-weighted/post-strategist scanner state, not as pure LLM-selected stock. |
| Scanner raw universe snapshot exists | `CONFIRMED` | `libs/runtime/scanner/output_payloads.py` emits `scanner_intrinsic_control_top20` and `pre_strategist_full_universe_snapshot`; `libs/runtime/q9_decision_snapshots.py` persists these into `scanner_control` and `scanner_pre_strategist_universe`. | Raw scanner and post-strategy ranking can be compared. Do not claim this data is missing. |
| Scanner control limitation exists | `CONFIRMED` | `q9_decision_snapshots.py` explicitly marks scanner control as `same_candidate_universe_ranking_only` and says candidate sourcing may already reflect Strategist guidance. | Full raw universe quality and same-candidate reranking are different questions. Keep them separate. |
| Runner-up / executed-symbol mismatch is normalized for reporting | `CONFIRMED` | `libs/reporting/trade_symbol_context.py::normalize_scanner_context_for_executed_symbol` preserves original scanner selected symbol and adds `selection_mismatch` when executed symbol differs. | Use mismatch fields to audit monitor/cascade execution rather than blaming Strategist or Commander by default. |
| Strategy horizon path exists | `CONFIRMED` | `libs/runtime/strategy_horizon_feedback.py`, `libs/runtime/monitor_strategy_frame.py`, `libs/runtime/exit_policy.py`, and reporting modules all carry `strategy_horizon` / `expected_hold_window`. | The problem is not absence of horizon fields. The problem is whether runtime enforcement and actual exits align with them. |
| Horizon enforcement is incomplete as a blanket rule | `PARTIAL` | `exit_policy.py` enforces min-hold/confirmation for `vwap_breakdown` and `intraday_low_break`; `monitor_strategy_frame.py` adjusts hold controls and exit policy by horizon; `quant/decision.py` can flag `early_exit_before_expected_min_hold`. | Do not assume every exit respects the 4-page/horizon intent. Audit by exit reason before changing behavior. |
| Cost floor is implemented and observable | `CONFIRMED` | `quant/factors.py`, `quant/decision.py`, `intraday_monitor_signals.py`, and `exit_policy.py` expose `cost_floor_state`, cost-adjusted edge, reward room, and cost-aware profit floor. | Cost floor should remain a hard requirement unless a separate benchmark proves an exception. |
| Entry quality versus hard gate visibility exists | `CONFIRMED` | `intraday_monitor_signals.py` records `entry_quality_score`, `breakout_score`, `breakout_path_ok`, `entry_hard_gate_passed`, and `entry_quality_*_but_hard_gate_failed`. | Reports can explain "quality high but gate failed"; use this to debug blocked opportunities. |

## Data Findings

### Q9 Five Valid Days

Source: `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/daily_ledger.json`.

| Day | Valid | +30m Alpha | Status | Root Cause |
| --- | --- | ---: | --- | --- |
| 2026-06-29 | no | n/a | insufficient | insufficient_comparable_forward_samples |
| 2026-06-30 | yes | +0.3091 | adds alpha | - |
| 2026-07-01 | yes | +0.0899 | adds alpha | - |
| 2026-07-02 | yes | +0.3556 | adds alpha | - |
| 2026-07-03 | yes | -1.1146 | no alpha | scanner_candidate_set_or_intrinsic_ranking_underperformed_fixed_baseline |
| 2026-07-06 | yes | +0.0689 | adds alpha | - |

Interpretation:

- Q9 did show relative alpha versus the Samsung/Hynix fixed baseline on the primary +30m horizon in 4 of 5 valid days.
- That does not prove positive absolute edge because the main returns were still negative after cost/slippage.
- 2026-07-03 remains the major failure day and points to scanner candidate set / intrinsic ranking weakness.

### Historical Prior

Source: `reports/evaluation/historical_q9_prior/historical_q9_prior_report.md`.

- Scope: 65 source days before 2026-06-29.
- Trades: 483 total / 452 eligible.
- Eligible win rate: 8.8%.
- Eligible average return: -1.5140%.
- Eligible profit factor: 0.0728.
- Integrity: 376 PASS / 106 WATCH / 1 FAIL.

Breakdowns:

| Bucket | Count | Win Rate | Avg Return | Profit Factor |
| --- | ---: | ---: | ---: | ---: |
| rank1 | 220 | 4.5% | -0.9324% | 0.0522 |
| rank2-3 | 99 | 10.1% | -2.7890% | 0.0605 |
| rank4-10 | 98 | 16.3% | -1.8456% | 0.0977 |
| breakout | 26 | 26.9% | -0.7802% | 0.4099 |
| defensive | 241 | 5.8% | -1.8022% | 0.0263 |
| pullback | 165 | 9.7% | -1.3088% | 0.0960 |
| before_min_hold | 99 | 8.1% | -1.4603% | 0.1254 |
| before_target_hold | 105 | 9.5% | -1.9245% | 0.0223 |

Top WATCH items:

- `exit_before_strategy_min_hold`: 113
- `exit_before_strategy_target_hold`: 105
- `sub_60_second_exit`: 87
- `horizon_violation_candidate`: 79
- `pnl_authority_weak`: 66

Interpretation:

- The current combined system does not have proven positive edge.
- The weakness predates the Q9 five-day freeze; it is not a one-week anomaly.
- Rank1 being less bad than lower ranks suggests rank/cascade discipline matters.
- Breakout is still negative but materially less bad than defensive and pullback in historical prior. It deserves diagnostic attention, not blind promotion.
- Horizon mismatch is real and repeated, but "hold longer" is not automatically proven because the `within_target_window` bucket is also negative.

### Q10/Q11/Q12 Controls

Q10 Samsung/Hynix baseline:

- Useful as a fixed-market benchmark.
- Not a production candidate by itself.
- Q9 sometimes beats it relatively, but both sides can still be negative after costs.

Q11 opening opportunity shadow:

| Day | Virtual Trades | Win Rate | Avg Net |
| --- | ---: | ---: | ---: |
| 2026-06-30 | 3 | 0.0% | -1.8594% |
| 2026-07-01 | 2 | 0.0% | -2.2884% |
| 2026-07-02 | 1 | 0.0% | -1.5466% |
| 2026-07-03 | 2 | 0.0% | -2.5957% |
| 2026-07-06 | 1 | 0.0% | -0.6353% |

Q12 BTC/Woori baseline, +5m:

| Day | Trades | Win Rate | Avg Net |
| --- | ---: | ---: | ---: |
| 2026-06-30 | 4 | 0.0% | -1.0892% |
| 2026-07-01 | 7 | 0.0% | -1.1254% |
| 2026-07-02 | 9 | 0.0% | -1.0351% |
| 2026-07-03 | 11 | 0.0% | -0.9391% |
| 2026-07-06 | 9 | 0.0% | -1.0851% |

Interpretation:

- Q11/Q12 are useful negative controls. They show that "opening shot" or "theme proxy" alone does not solve the cost-adjusted edge problem.
- They should remain shadow controls unless their entry/exit rules are redesigned and then retested as separate research modules.

## Current Conclusions We Can Already Close

1. Do not extend Q9 just to collect more of the same evidence.
2. Do not blame Commander as a stock selector without symbol-change evidence.
3. Do not treat Strategist B as pure LLM stock picking; it is a post-strategy scanner/ranking state.
4. Do not promote Q10/Q11/Q12 as execution policy.
5. Keep cost floor hard.
6. Treat scanner candidate quality/ranking and horizon/timing alignment as the next focused patch area.
7. Regenerate or fix Q9 closure markdown because it drifted from the authoritative JSON ledger.

## What Code Can Settle Before More Trading

| Question | How to settle now |
| --- | --- |
| Does Strategist directly pick symbols? | Trace scanner output, `selected`, `ranked_candidates`, post-scanner refresh, and report `selection_mismatch`; document authority chain. |
| Does Commander change symbols? | Compare `selected.symbol`, `monitor_output.selected_symbol`, first intent symbol, and `commander_final.candidate_symbol` across Q9 snapshots. |
| Is scanner score overloaded? | Audit whether raw ranking score, strategy-weighted score, and execution/cost score are stored as separate fields. If not, split observability first. |
| Are 4-page/horizon hold windows being respected? | Use `strategy_horizon_feedback`, `exit_vs_strategy`, `horizon_contract`, and broker hold seconds. Group by exit reason before behavior changes. |
| Are reports trustworthy? | Add a deterministic drift check: markdown closeout values must match daily ledger JSON for alpha, valid-day count, evidence status, and root cause. |

## Patch Candidates, Ordered

1. **Evaluation artifact authority patch**
   - Regenerate `q9_closure_summary_2026-07-06.md` from `daily_ledger.json`.
   - Add drift check so markdown cannot silently disagree with ledger JSON.
   - Behavior change: none.

2. **Selection authority audit patch**
   - Produce a read-only report for each decision window:
     - raw scanner top1
     - post-strategy top1
     - selected symbol
     - monitor intent symbol
     - commander candidate symbol
     - executed symbol
     - mismatch reason
   - Behavior change: none.

3. **Scanner score decomposition patch**
   - Preserve existing scanner score.
   - Add read-only fields for:
     - `raw_momentum_quality_score`
     - `strategy_context_score`
     - `cost_horizon_fit_score`
     - `execution_readiness_score`
   - Behavior change should be off until the audit proves the decomposition is reliable.

4. **Horizon compliance report patch**
   - Group exits by strategy horizon, expected hold window, actual hold, exit reason, and forward returns at target hold.
   - Only after this should any min-hold enforcement be changed.

5. **Targeted behavior patch**
   - Pick exactly one behavior change after the above reports:
     - scanner rank/cascade discipline, or
     - entry timing gate, or
     - horizon-specific exit handling.
   - Do not bundle all three.

## Guardrail

The next patch should not be "more evaluation" in the abstract. It should either:

- fix evaluation/report authority, or
- add a read-only audit surface that answers one specific unresolved question, or
- change one proven failure point and define the verification metric before deployment.

