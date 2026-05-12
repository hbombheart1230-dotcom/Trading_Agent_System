# 2026-05-11 Pending Order Stale Guard

## Context

- Live runtime selected `078890` after the `078890` closeout cleanup, but monitor blocked the new entry with `same_symbol_pending_buy`.
- The order had already finished, so the block was a stale/historical order-row interpretation problem, not a real pending buy.

## Patch

- Centralized account order pending detection in `graphs/nodes/skill_contracts.py`.
- Scanner now counts only pending account order rows for `skill_open_orders`.
- Scanner marks `skill_open_orders_pending_only=true` when writing the feature.
- Monitor no longer hard-blocks on legacy `skill_open_orders` unless it is explicitly pending-only.
- Monitor sell guard now uses the same pending-only interpretation, so filled historical rows cannot block an exit as `sell_guard_open_order_pending`.
- Commander closeout pending-buy cancellation now uses the same pending-order interpretation.

## Pending Definition

- Pending if explicit remaining quantity is greater than zero.
- Pending if order quantity is greater than filled quantity and status is explicitly working/open/accepted.
- Not pending if filled, completed, cancelled, rejected, denied, blocked, or historical row lacks pending evidence.

## Verification

- `venv\Scripts\pytest.exe -q tests/test_m22_skill_contracts.py tests/test_m22_skill_native_scanner_monitor.py`
  - `17 passed`
- `venv\Scripts\pytest.exe -q tests/test_m21_commander_runtime_entry.py -k closeout_cancels_pending_buy_before_monitor`
  - `1 passed, 75 deselected`
- `venv\Scripts\pytest.exe -q tests/test_m22_skill_contracts.py tests/test_m22_skill_native_scanner_monitor.py tests/test_m29_3_monitor_exit_policy.py`
  - `34 passed`

## Live Check

- Restarted live runtime after the entry-side patch.
- `078890` was selected through cascade and BUY order `0083445` was accepted at 10:36:53 KST, confirming the stale finished-order row no longer blocked entry as `same_symbol_pending_buy`.
- Restarted again after the sell-guard patch so the running monitor uses the same pending-only order interpretation for exits.
- Runtime lock owner after restart: PID `26440`; heartbeat observed at `2026-05-11T01:45:35+00:00`.

## Live Risk

- Current position capacity is full at `RISK_MAX_POSITIONS=3`, so new buys should pause until one position exits.
- Watch exits closely: completed historical order rows should no longer block valid stop-loss/protective sells.

## Follow-up: Candidate Expansion And Holding Focus

### Context

- Later live cycles held only `000660` while Scanner kept selecting fresh candidates such as `078890`.
- The hard position cap was not the blocker: `.env`/runtime allowed `RISK_MAX_POSITIONS=3`, and the live state had one open position.
- Commander was treating a `preflight_blocked` runtime label as `risk_mode=blocked` even when `portfolio_preflight.blocked=false` and position capacity remained.
- That clamped candidate watching to rank 1 / no runner-ups, so Monitor repeatedly evaluated only the first fresh candidate while `000660` remained the position focus.
- Monitor canonical output used the held position as the representative symbol, which made it look like fresh candidates were not being checked.

### Patch

- Commander now treats `preflight_blocked` as a hard risk block only when portfolio preflight is actually blocked or no position capacity remains.
- When repeated expandable blockers occur in a supportive, capacity-available session, Commander can override an overly narrow strategist candidate-watch proposal and reopen rank expansion to top 10 / 9 runner-ups.
- Monitor output now records `monitor_focus_context` with separate fields for:
  - `scanner_selected_symbol`
  - `entry_candidate_symbol`
  - `entry_final_symbol`
  - `position_focus_symbol`
  - entry blocker / cost-adjusted edge details
  - exit/hold reason for the open position
- Canonical monitor artifacts and AI trade-report input now carry the same focus context.
- Stage 3 hold-review prompt now explicitly forbids borrowing unrelated runner-up or market theme labels for the held symbol.

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py graphs\nodes\monitor_node.py graphs\nodes\strategist_node.py libs\contracts\agent_outputs.py libs\reporting\trade_report_ai.py libs\reporting\trade_report_markdown_clean.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py`
  - `77 passed`
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py`
  - `97 passed`
- `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py`
  - `40 passed`

### Live Check Needed

- After restart, confirm the next commander artifact no longer reports `risk_mode=blocked` solely because `status=preflight_blocked` while `portfolio_preflight.blocked=false`.
- Confirm the next monitor artifact includes `monitor_focus_context` and clearly separates fresh entry candidate from held-position focus.
- Confirm `entry_control.max_priority_rank` expands again when repeated blockers persist and position capacity remains.

## Follow-up: Trade Summary Candidate-Flow Alignment

### Context

- `TRD_20260511_078890_02` summary mixed two different decision contexts in the `종목 선정 흐름` section.
- The actual trade selection path was `000660` top-pick hold -> `078890` fallback/reassessment entry.
- A later unrelated monitor cascade from a capacity-full cycle reported `005930` with `max_positions_reached`.
- The summary renderer appended that later cascade as `실제 확인: 차순위 미실행` and `최종 후보: 005930`, contradicting the actual traded symbol `078890`.

### Patch

- Added candidate-cascade symbol matching in `libs/reporting/trade_report_markdown_clean.py`.
- When a trade already has an explicit monitor fallback/reassessment selection path, summary candidate-watch lines are rendered only if the cascade symbols match the traded symbol.
- Recovered/partial exit summaries use the same guard, because those reports are about held-position cleanup rather than a fresh entry candidate.
- General candidate-watch summaries remain unchanged for reports without an explicit fallback/reassessment path.

### Verification

- Added regression coverage for a fallback trade where a later unrelated `max_positions_reached` cascade points at another symbol.
- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_markdown_clean.py tests\test_trade_report_ai.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_trade_report_ai.py`
  - `124 passed`

## Follow-up: Overnight Carryover Trade Summary Date Basis

### Context

- `reports/trades/2026-05-11/0900/TRD_20260511_005930_01/reports/ai_trade_summary.md` was a Monday partial sell of a position carried from the prior Friday.
- The summary showed the current-day scanner/candidate context (`078890`) as if it explained `005930`, which made the selection flow and date basis inaccurate.
- `ai_trade_report.json` already had carryover evidence through `carry_state=multi_session_stale`, `carry_risk_bias=urgent_exit_review`, and `actual_hold_sec=249265`.
- Event logs also confirm the Friday closeout decision: `2026-05-08 15:29:47 KST`, monitor reason `eod_carry_approved`, active exit axis `Carry Overnight Approved`, `exit_triggered=false`.

### Patch

- Added carryover detection to `libs/reporting/trade_report_markdown_clean.py`.
- Carryover sell summaries now:
  - mark the report as an overnight/weekend carryover exit,
  - display estimated hold start and exit date/time using `actual_hold_sec` plus the exit timestamp,
  - suppress unrelated current-day scanner candidate lines,
  - exclude same-day entry/scanner assessment from the summary input,
  - add an LLM hard constraint to keep carryover date basis separate from current-day exit context.
- Updated the generated `005930` summary to include the confirmed 2026-05-08 overnight approval reason and remove the misleading `078890` candidate-flow explanation.

### Verification

- Added regression coverage for a Friday-to-Monday carryover sell where a later same-day candidate cascade points to another symbol.
- `venv\Scripts\python.exe -m pytest tests/test_trade_report_ai.py -q`
  - `125 passed`

## Follow-up: Constructive Market Entry Scope And Policy Unit Normalization

### Context

- After the `000660` closeout, live logs showed a valid `078890` BUY at 13:56 KST, but subsequent cycles looked quiet because open-position reports are not generated immediately.
- The 13:59 KST commander artifact still used `risk_mode=defensive` even though market sentiment was bullish and position capacity remained.
- The defensive state came from an inactive macro stress overlay: `stress_flags=["dollar_strength"]` while `macro_stress_overlay.active=false`.
- The same cycle also showed `policy_fallback_reason=invalid_fields=min_extended_from_vwap_pct,...` because the strategist expressed entry-policy percentage thresholds in percent units (`3.0` meaning `3%`) and the validator interpreted them as decimal ratios.

### Patch

- `graphs/commander_runtime.py`
  - Ignores macro stress flags when `macro_stress_overlay.active=false`, so minor inactive overlays no longer force `risk_mode=defensive`.
  - This lets bullish/neutral, capacity-available sessions use the repeated-blocker expansion path again.
- `libs/runtime/monitor_policy.py`
  - Normalizes out-of-bound `*_pct` entry-policy fields from percent units to decimal ratios when the converted value is within the valid policy bounds.
  - Example: `max_extended_from_vwap_pct=3.0` becomes `0.03`, `pullback_min_pct=0.5` becomes `0.005`.

### Verification

- Added regression coverage for percent-unit policy normalization.
- Added regression coverage for inactive macro stress not clamping candidate expansion in constructive sessions.
- `venv\Scripts\python.exe -m py_compile libs\runtime\monitor_policy.py graphs\commander_runtime.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_m18_market_scan_candidates.py tests/test_monitor_feedback_adaptive_policy.py -q`
  - `17 passed`

## Follow-up: LLM Report Execution Classification

### Context

- `reports/llm/2026-05-11` mixed completed trade runs, no-trade runs, and manual/test artifacts in one flat run_id list.
- This made it look like strategy stage 2 was missing, even though the stage 2 artifacts are stored as `strategist_stage2_selected_symbol`.
- As of this check, stage 2 exists in 66 LLM run folders for 2026-05-11.

### Patch

- Added `libs/runtime/llm_report_classifier.py`.
  - `trade_executed`: canonical executor action is BUY/SELL and execution is successful.
  - `no_trade`: canonical run exists but no BUY/SELL completed, including WAIT/NOOP cycles.
  - `manual_or_test`: synthetic folders or folders without a matching canonical run.
- Added `scripts/organize_llm_reports.py` for manual backfill and operator cleanup.
- Updated LLM artifact path resolution so already-classified runs are read/written under the grouped folder.
- Executor artifact writing now classifies the current run immediately after execution state is persisted.
- M13 live loop now also classifies the current run at the end of each completed cycle, so runs without executor output are still moved into `no_trade`.
- Existing JSON refs inside moved LLM artifacts are rewritten to the new grouped path.

### 2026-05-11 Backfill

- `reports/llm/2026-05-11/trade_executed`: 15 runs
- `reports/llm/2026-05-11/no_trade`: 94 runs
- `reports/llm/2026-05-11/manual_or_test`: 19 runs
- `reports/llm/2026-05-11/README.md` and `_classification_index.json` were generated.
- Live verification: after restart, run `a75e153c6aa2443ebba2123bce64932a` was automatically moved from the date root into `no_trade` at cycle completion.
- The generated classification README now updates through the same automatic classification path.

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\pipelines\m13_live_loop.py libs\runtime\llm_report_classifier.py libs\runtime\canonical_artifacts.py scripts\organize_llm_reports.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_m13_live_loop.py tests/test_canonical_artifact_validation.py -q`
  - `14 passed`

## Follow-up: Stage-Specific Strategist Summary Rendering

### Context

- `reports/llm/2026-05-11/trade_executed/4cde9a40d2c548d9ab52f7f3153ff4e0/strategist/strategist_summary.md` looked sparse because the legacy `strategist/` artifact for that run contained a stage 3 hold review, not a stage 1 market strategy frame.
- The previous summary renderer treated every `strategist/response.json` as a market-frame response, so fields such as `selected_themes`, `playbook`, and `monitor_entry_policy` appeared empty.
- The actual LLM response had a valid stage 3 decision: `hold_review_decision=tighten_exit`, `exit_pressure=medium`, `thesis_status=weakened`, `next_check_minutes=5`.

### Patch

- `libs/reporting/strategist_llm_summary.py`
  - Resolves canonical strategist paths when LLM artifacts are under grouped folders such as `trade_executed/<run_id>/...`.
  - Detects non-market-frame strategist stages and renders a stage-specific summary instead of the market-frame template.
  - Stage 3 summaries now surface decision, exit pressure, thesis status, monitor adjustments, next check interval, and priority exit triggers.
- `libs/runtime/canonical_artifacts.py`
  - Generates `strategist_summary.md/json` for stage-specific strategist artifact folders as well as the legacy `strategist/` folder.
- Regenerated both:
  - `.../strategist/strategist_summary.md`
  - `.../strategist_stage3_hold_review/strategist_summary.md`

### Encoding Check

- The stage 3 `reason` text is valid UTF-8 in `response.json` and in the regenerated Markdown.

## Follow-up: Daily Summary Residual Position Reconciliation

### Context

- `reports/operator_summary/daily/2026-05-11/daily_summary.md` still listed `005930` as a residual holding even though `TRD_20260511_005930_04` recorded a 10-share `eod_flat` SELL.
- The residual-holding section was reading `data/state.json` directly and did not reconcile `flatten_before_close` decisions against same-day lifecycle close evidence.
- Residual holdings without an overnight decision, such as the remaining `000660` state row, rendered with a blank reason.

### Patch

- `libs/reporting/operator_period_summary.py`
  - `build_residual_positions_payload()` now accepts `day`.
  - For `flatten_before_close`/closeout-style actions, it checks same-day `lifecycle_bundle.json` files for matching full SELL evidence before rendering a residual holding.
  - Matching fully sold rows are moved to `reconciled_closed_positions` instead of `positions`.
  - Residual rows with no overnight decision now show `오버나이트 판단 기록 없음`.
- `scripts/generate_daily_report.py`
  - Passes the report day into residual-position construction.
  - Renders the same reconciliation note in the daily report residual section.
- Regenerated `reports/operator_summary/daily/2026-05-11/daily_summary.md/json`.

### Verification

- `venv\Scripts\python.exe -m py_compile libs\reporting\operator_period_summary.py scripts\generate_daily_report.py tests\test_operator_summary_reports.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_operator_summary_reports.py tests\test_daily_report.py -q`
  - `23 passed`
- Regenerated daily summary now shows:
  - `005930` excluded with `장중 청산 확인`
  - `000660` as the only residual row with `사유 오버나이트 판단 기록 없음`
- The earlier mojibake observation came from PowerShell `Get-Content` rendering in the command output path, not from the stored report file.
- Added a Korean reason regression case so future stage-specific summaries preserve Korean text.
- A scan of `reports/llm/2026-05-11/**/strategist_summary.md` found no common mojibake markers after regeneration.

### Verification

- Added regression coverage for classified-folder canonical lookup and stage 3 hold-review summary rendering.
- `venv\Scripts\python.exe -m py_compile libs\reporting\strategist_llm_summary.py libs\runtime\canonical_artifacts.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_strategist_llm_summary.py tests/test_canonical_artifact_validation.py -q`
  - `16 passed`
- `venv\Scripts\python.exe -m pytest tests/test_strategist_llm_summary.py -q`
  - `5 passed`

## Follow-up: 073490 Truth Surface And Missed Profit Review

### Context

- `TRD_20260511_073490_01` initially showed `매도가 -`, `실현 손익 확인 불가`, and `관측 손익률 -1.86%`.
- The sell order itself was not missing. Executor output showed `모의투자 매도주문완료`, order `0167527`, qty `56`.
- The original report had `broker_day_match_mode=ambiguous_symbol_rows`, because `ka10077` returned 3 same-symbol rows and the older report input could not select the exact row.
- The displayed `-1.86%` was not entry-price PnL. It was peak drawdown: `52,900` vs peak `53,900`.

### Patch

- Fallback mark-only PnL now uses `current_or_mark_price` against entry/average price.
- `current_drawdown` / `peak_drawdown` is no longer accepted as fallback PnL.
- Summary wording changed from `체결 미확인` to `체결가 미확정` when the order exists but exact fill price is not authoritative yet.
- Batch regeneration now creates all report output parent directories before writing.

### Regeneration Result

- Rebuilt `TRD_20260511_073490_01` from `lifecycle_bundle`.
- New match mode: `symbol_split_buy_sell_qty_exact`.
- Truth Surface now shows:
  - buy/sell: `53,000 / 53,000`
  - realized PnL: `-26,696 (-0.90%)`
  - fee/tax: `20,760 / 5,936`
  - cost drag: `0.90%`

### Missed Profit Finding

- Entry: `14:19:28 KST`, `53,000`, qty `56`.
- `14:37:49 KST`: monitor saw `53,600`, gross `+1.13%`; this was below the cost-aware/partial take-profit floor `1.20%`.
- `15:06:13 -> 15:11:25 KST`: no `073490` monitor evaluation occurred while the position peak moved to `53,900`.
- At the next `073490` check, current price was already back to `52,900`, so profit-take triggers could no longer execute at the peak.
- `15:11:25 KST`: peak drawdown `-1.86%`, confirmation `1/2`.
- `15:12:00 KST`: peak drawdown confirmation `2/2`, sell submitted.

### Runtime Exit-Priority Patch

- Added `commander.route.pre_entry_exit_sweep_enabled` with code default `true`.
- When any position is open, integrated runtime now runs one pre-entry open-position exit check before strategist/scanner work.
- If the pre-entry check produces an approved `SELL`, runtime executes that sell immediately and ends the tick on `integrated_chain_pre_entry_exit_sweep`.
- If there is no exit signal, runtime restores scanner/monitor transient state and continues the original strategist -> scanner -> monitor flow.
- Open-position focus sorting now prioritizes unresolved closeout, carry risk, profit-protection candidates, peak giveback, loss risk, and oldest exit-sweep check.
- This directly addresses the `073490` gap where scanner/strategy work allowed a held symbol to go several minutes without exit evaluation during a profit spike.

### Verification

- `venv\Scripts\python.exe -m pytest tests/test_trade_report_ai.py -q`
  - `126 passed`
- `venv\Scripts\python.exe -m pytest tests/test_run_ai_trade_report_batch.py tests/test_trade_regeneration_truth.py -q`
  - `19 passed`
- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py tests\test_m21_commander_runtime_entry.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - `79 passed`

## Follow-up: Overnight Decision Record Visibility

### Context

- `reports/operator_summary/daily/2026-05-11/daily_summary.md` showed `000660` as residual holding with only `사유 오버나이트 판단 기록 없음`.
- The state snapshot had no `overnight_decision_by_symbol["000660"]`.
- `000660` last monitor state was `2026-05-11 15:19:19 KST`, just before the normal EOD carry decision window starting at 15:20.
- After that, EOD checks focused on `005930`, so `000660` did not get a persisted carry/flatten decision record.

### Patch

- Residual-position payload now attaches missing-decision diagnostics from `monitor_last_state_by_symbol`.
- Daily summary and daily report now render a `판단 기록 상태` line for residual positions with no persisted overnight decision.
- The diagnostic includes last monitor timestamp, last posture/reason, blocking axis, and inferred missing reason.
- Existing lifecycle reconciliation still excludes same-day fully sold symbols, so `005930` remains excluded from residual holdings.
- Runtime monitor now performs an EOD carry-decision sweep for every open position when the EOD window is active.
- The sweep persists `overnight_decision_by_symbol` for all held symbols, not just the currently selected exit-focus symbol.

### Verification

- Regenerated `reports/operator_summary/daily/2026-05-11/daily_summary.md/json` and `daily_report.md/json`.
- `000660` now shows:
  - `마지막 모니터 2026-05-11 15:19:19 KST`
  - `마지막 판단 HOLD(hold)`
  - `차단축 pullback_structure`
  - `EOD 판단창(15:20 이후) 재점검 없음`
- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py tests/test_daily_report.py -q`
  - `23 passed`
- `venv\Scripts\python.exe -m pytest tests/test_monitor_exit_guard.py tests/test_operator_summary_reports.py tests/test_daily_report.py -q`
  - `121 passed`
- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\reporting\operator_period_summary.py scripts\generate_daily_report.py`
  - passed

## Follow-up: Daily Summary Symbol Section Check

### Context

- `daily_summary.json` contained `symbol_summary`, but `daily_summary.md` showed an empty `종목별 요약` section.
- The daily report renderer reused the local variable name `symbols` for reconciled residual symbols, which shadowed the original symbol-summary list.

### Patch

- Renamed the reconciled residual symbol text variable so the symbol-summary list remains intact.
- Added a regression assertion that a residual open symbol still appears in `종목별 요약`.

### Verification

- Regenerated `reports/operator_summary/daily/2026-05-11/daily_summary.md/json` and `daily_report.md/json`.
- `daily_summary.md` now shows:
  - `005930: 거래 3건 / 완료 2건 ...`
  - `078890: 거래 3건 / 완료 3건 ...`
  - `115160`, `000660`, `073490` rows
- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py tests/test_daily_report.py -q`
  - `23 passed`
- `venv\Scripts\python.exe -m py_compile libs\reporting\operator_period_summary.py`
  - passed

## After-Close Review: Truth, Partial Exit, Sell Guard, Profit Giveback

### Context

- Market was closed, so runtime-facing fixes were patched without live order pressure.
- Today still had three review risks:
  - partial/split lifecycle rows could distort daily win-rate and symbol summaries;
  - a failed duplicate sell path showed broker rejection `매도가능수량 부족`;
  - `073490` gave back a profitable spike because peak-drawdown confirmation waited after the trade had already fallen below the cost-aware profit floor.

### Today Metrics After Regeneration

- `reports/operator_summary/daily/2026-05-11/daily_summary.json`
  - trades: `10`
  - closed trades: `8`
  - return samples: `8`
  - win/loss: `3/5`
  - win rate: `37.5%`
  - average closed return: `-0.0702%`
  - realized partial/recovered exits: `2`, average `4.073%`
- `TRD_20260511_115160_01` was regenerated from broker day truth:
  - buy/sell: `6,906 / 6,960`
  - realized PnL: `-116 (-0.11%)`
  - fee/tax: `720 / 208`
  - previous invalid `0` sell price and `-100%` display are no longer present.

### Patch

- Truth Surface:
  - treats non-positive broker fill price as missing, not as a real sell price;
  - suppresses invalid fallback/estimate `-100%` when both broker fill and mark price are unusable;
  - re-derives display-only fallback PnL from valid monitor/account mark when available.
- Trade summary cost analysis:
  - ignores non-positive sell prices for price-move and notional calculations.
- Operator summary:
  - partial/recovered exits are classified only by `status=partial` or `trade_origin=recovered_partial`;
  - `lifecycle_completeness=partial` is not used as a partial-exit marker because today's regenerated lifecycle bundles use it as a recovery-quality flag across normal rows too.
- Execution:
  - added a recent SELL guard to block duplicate full-exit sells before broker/account position reflection catches up;
  - partial sell followed by remaining-quantity sell is still allowed.
- Exit policy:
  - added urgent profit-protection for peak drawdown after max runup crossed the cost-aware floor and current gross PnL fell back below that floor;
  - urgent path bypasses the extra peak-drawdown confirmation tick.
- Report regeneration:
  - targeted `--trade-id` runs refresh only affected symbols by default;
  - `--refresh-all-symbols` remains available when a full symbol refresh is explicitly needed.

### Verification

- `venv\Scripts\python.exe -m pytest tests/test_run_ai_trade_report_batch.py tests/test_trade_regeneration_truth.py tests/test_trade_report_ai.py::test_truth_surface_ignores_zero_fill_snapshot_estimate_for_fallback_pct tests/test_operator_summary_reports.py::test_operator_daily_summary_reads_partial_marker_from_daily_trade_lifecycle tests/test_execute_from_packet.py::test_execute_from_packet_blocks_recent_full_sell_before_position_reflects tests/test_execute_from_packet.py::test_execute_from_packet_allows_recent_partial_sell_remaining_qty tests/test_strategy_sizing_exit_upgrade.py::test_exit_policy_peak_drawdown_protects_cost_floor_runup_giveback tests/test_monitor_exit_guard.py::test_monitor_peak_drawdown_profit_protection_urgent_bypasses_extra_confirmation -q`
  - `25 passed`
- `venv\Scripts\python.exe -m py_compile libs\reporting\report_truth_surface.py libs\reporting\trade_report_markdown_clean.py libs\reporting\operator_period_summary.py graphs\nodes\execute_from_packet.py libs\runtime\exit_policy.py graphs\nodes\monitor_node.py scripts\run_ai_trade_report_batch.py`
  - passed
- Regenerated:
  - `TRD_20260511_115160_01`
  - `TRD_20260511_005930_04`
  - `reports/operator_summary/daily/2026-05-11/daily_summary.md/json`

### Remaining Watch Items

- Targeted deterministic regeneration still took about `135s` for two trades. Scope is now narrower, but report input rebuild and broker-truth matching still need profiling if this becomes a daily bottleneck.
- Mock-investment fee/tax drag is still about `0.90%` in several Truth Surface rows. Entry/exit cost gates are aligned to that reality, but this should be rechecked if the broker cost basis changes.
- `000660` remained as the only residual holding in today's already-finished report and still has no persisted overnight decision record for the completed run. Runtime EOD sweep was patched earlier, so the next live EOD needs validation.
- The win-rate problem is not only reporting. Main trading issue today remains poor net edge after cost: several entries had positive gross movement but not enough move to clear the cost drag before exit pressure appeared.

## After-Close Patch: Stage 2 Scanner Context Alignment

### Context

- 4stage LLM artifacts were being written, but Stage 2 selected-symbol refresh input was sometimes weak.
- In one live sample, the actual scanner rank #1 was `033170`, while the selected/cascade candidate was `078890`.
- The Stage 2 prompt flattened the selected candidate back into `rank=1` with missing score, so the strategist could not clearly compare "scanner rank #1" versus "actual selected candidate".

### Patch

- Post-scanner candidate snapshots now preserve `score_total`, `post_adjust_score_total`, `risk_score`, `confidence`, compact score breakdown, and scanner reason fields.
- Stage 2 refresh context now separates:
  - `actual_selected_candidate`
  - `scanner_rank1_candidate`
  - `scanner_top_candidates`
  - `scanner_runner_ups`
  - `selected_symbol_was_rank1`
  - `stage2_context_quality`
- The old `scanner_primary_candidate` field remains backward-compatible as the actual selected candidate.
- Strategist LLM payload, compact payload, trace input, and `q15_commander_refresh_context` now keep those fields so reports and artifacts can explain why a non-rank-1 candidate was reviewed.

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py graphs\nodes\strategist_node.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_m21_commander_runtime_entry.py::test_post_scanner_snapshot_keeps_scanner_rank1_separate_from_actual_selected tests/test_strategist_frame_llm_integration.py::test_strategist_llm_payload_uses_post_scanner_refresh_symbol_from_strategy_context tests/test_strategist_frame_llm_integration.py::test_stage2_selected_symbol_contract_is_preserved_and_mapped_to_watch_policy tests/test_strategist_frame_llm_integration.py::test_stage_specific_llm_messages_match_4stage_contracts -q`
  - `4 passed`
- `venv\Scripts\python.exe -m pytest tests/test_strategist_frame_llm_integration.py -q`
  - `40 passed`
- `venv\Scripts\python.exe -m pytest tests/test_m21_commander_runtime_entry.py -q`
  - `80 passed`

## After-Close Design Note: Scanner / Monitor Role Boundary

### Decision

- Scanner should use chart context only as soft ranking bias.
- Monitor remains the hard entry/exit decision engine.
- Overlap is intentional but authority must differ:
  - Scanner: "is this worth watching?"
  - Monitor: "can this be bought/sold now?"

### Patch Direction For Later

- Keep `entry_compatibility_score` / `entry_compatibility_bias` as bounded Scanner-side Monitor-readiness estimates.
- Surface a clearer `scanner_chart_fit_score` / `scanner_chart_fit_components` field later so reports do not confuse Scanner ranking with Monitor entry approval.
- Prevent Scanner from hard-rejecting ordinary candidates only because VWAP reclaim, breakout, volume confirmation, or pullback timing is not ready.
- Add tests that prove Scanner soft bias can move rank, but Monitor can still block the selected candidate.

### Reference

- `docs/strategy_horizon_feedback/scanner_monitor_role_boundary_patch_plan_2026-05-11.md`

## After-Close Design Note: Strategy Horizon Visibility

### Finding

- Today's trade artifacts captured `strategy_horizon` values such as `scalp`, `intraday`, and `overnight_probe`.
- The main operator-facing `ai_trade_summary.md` files did not surface those values.
- The current field is `strategy_horizon`, not `primary_horizon`.
- Commander currently keeps horizon behavior observation-only:
  - `observability_only=true`
  - `allow_behavior_change=false`
  - `do_not_force_hold=true`

### Superseded Patch Direction

- Add a report section showing:
  - Strategist proposed horizon
  - Commander applied horizon
  - cap reason, if any
  - expected hold window
  - actual hold duration
  - exit-vs-horizon alignment
- Superseded by the later after-close patch below: horizon is still not a forced hold rule, but Commander now translates it into bounded monitor/scanner/report guidance.

### Priority Decision

1. Monitor first: cost-aware exit, profit capture, hold review cadence, horizon-vs-actual-hold reporting.
2. Scanner second: soft chart-fit scoring, candidate quality, rank #1 versus actual selected candidate clarity.
3. Strategist third: clearer horizon rationale and Stage 2 selected-symbol comparison quality.

### Reference

- `docs/strategy_horizon_feedback/strategy_horizon_report_visibility_and_patch_priority_2026-05-11.md`

## After-Close Patch: Chart Structure Logic + Horizon Translation

### Scope Correction

- Monitor and Scanner are not just report-visibility changes.
- Monitor/Scanner now strengthen the calculation layer so the runtime sees chart context closer to how a human would read a short-term chart.
- Strategist horizon remains proposed by the strategist, but Commander now translates it into concrete runtime handoff fields that Monitor and reports can consume.

### Monitor

- `chart_structure_features` now adds a `human_chart_context` block:
  - VWAP reclaim persistence
  - VWAP breakdown persistence
  - MA bullish/bearish persistence
  - volume expansion persistence
  - recent-high gap and late-entry risk
  - swing-low above VWAP
  - higher-low continuation
  - box breakout/retest hold
  - entry chart score
  - exit risk score
- `evaluate_intraday_entry_signal` consumes this context in `score_breakdown`.
- This strengthens scoring and visibility, but does not convert a legacy WAIT into BUY only because score passed. The existing hard entry contract remains intact.

### Scanner

- Scanner compatibility now blends monitor-readiness with chart-fit when minute data is available.
- Added:
  - `scanner_chart_fit_score`
  - `scanner_chart_fit_authority=soft_rank_bias_only`
  - `scanner_chart_fit_components`
  - `scanner_chart_fit_penalty`
- Scanner still uses this only as bounded ranking bias. Monitor remains the buy/sell authority.

### Strategist Horizon

- `strategy_horizon_feedback` now carries `behavior_translation` as a normalized proposal artifact.
- `commander_horizon_policy` now carries the Commander-owned applied translation:
  - scanner scope bias
  - monitor review cadence
  - stale hold review cadence
  - hold-control bias
  - exit-policy bias
  - profit-management style
  - overnight allowance flag
- `allow_behavior_change` remains false to prevent forced holding.
- `allow_behavior_translation=true` records that Commander may apply the horizon as hold-control / exit-policy / reporting guidance.
- Monitor hold controls and exit policy now read the Commander horizon translation.
- Trade reports now surface the horizon translation alongside proposed/applied horizon and expected/actual hold comparison.

### Verification

- `venv\Scripts\python.exe -m py_compile libs\runtime\chart_structure_features.py libs\runtime\intraday_monitor_signals.py graphs\nodes\scanner_node.py libs\runtime\strategy_horizon_feedback.py graphs\nodes\monitor_node.py graphs\nodes\strategist_node.py graphs\commander_runtime.py libs\reporting\trade_report_markdown_clean.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_chart_structure_features.py tests\test_strategy_horizon_feedback.py -q`
  - `12 passed`
- `venv\Scripts\python.exe -m pytest tests\test_intraday_monitor_signals.py -q`
  - `64 passed`
- `venv\Scripts\python.exe -m pytest tests\test_scanner_monitor_compatibility.py -q`
  - `8 passed`

### Remaining Watch Items

- Next live run must confirm `scanner_chart_fit_score` appears in scanner artifacts and that it changes ranking only as a soft bias.
- Next trade report must confirm the Strategy Horizon section shows both the proposed/applied horizon and the applied horizon translation.
- Horizon translation should be reviewed after several trades; if it makes exits too tight for `scalp` or too loose for capped long-horizon proposals, adjust the Commander translation table rather than adding env flags.

## Planning Note: Commander Daily Profit Guard

### Decision

- This is not implemented yet.
- Development is intentionally deferred until mock-investment runtime is more stable.
- Ownership should be Commander, not Strategist.

### Policy Direction

- Strategist may recommend a daily profit stop based on market condition.
- Commander must translate it into final `%` and KRW thresholds using:
  - account equity
  - net realized PnL after fee/tax/slippage
  - estimated round-trip cost
  - minimum meaningful profit amount
- Hard lock should block new BUY only.
- Existing positions should continue to be managed by Monitor exit policy.

### Reference

- `docs/commander_control/daily_profit_guard_policy_draft_2026-05-11.md`
