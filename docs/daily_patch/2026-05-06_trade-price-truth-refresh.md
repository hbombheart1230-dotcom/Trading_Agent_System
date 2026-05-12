# 2026-05-06 - Trade Price Truth Refresh

## Context

`TRD_20260506_018880_09` summary showed buy price `5,394` but missing sell price even though the monitor snapshot had `current_price=5,440` and the order quantity had increased to `275`.

The quantity change was not the direct display bug. It made the trade larger and easier to notice, but the bad report came from two price-source issues:

- the initial broker-day match was `ambiguous_symbol_rows`, so the report could not yet confirm a sell fill;
- when broker sell fill was unavailable, some paths fell back to average entry price `5,394` as if it were the sell/order reference.

## Patch

- SELL intents now prefer monitor intent `meta.price/current_price/raw_price` before stale `market_snapshot.price`.
- Executor order construction now uses monitor intent meta price when `intent.price` is missing.
- Report backfill no longer treats average entry price as the SELL price before checking monitor current/reference price.
- Post-exit shadow base price now prefers confirmed fill, then monitor exit price, then average price.
- Summary markdown separates broker-confirmed sell fill from monitor reference price when the broker fill is still missing.

## Report Refresh

Regenerated:

- `reports/trades/2026-05-06/TRD_20260506_018880_09/reports/ai_trade_summary.md`
- `reports/trades/2026-05-06/TRD_20260506_018880_10/reports/ai_trade_summary.md`
- all 2026-05-06 trade summaries with `--no-llm`

Updated Truth Surface:

- buy/sell: `5,394 / 5,410`
- realized PnL: `-8,980 (-0.61%)`
- fee/tax: `10,350 / 2,964`
- price change: `+0.29%`
- cost drag: `13,314 (0.90%)`

Interpretation:

- The trade price rose from `5,394` to `5,410`, but the simulated fee/tax drag was larger, so net result is still a loss.
- The old `5,394 / -` display was stale/incomplete report state, not a valid final execution summary.

## Broker API Split-Fill Truth

`TRD_20260506_018880_10` still showed realized PnL and fee/tax as unavailable after regeneration even though Kiwoom `ka10077` had the values.

Root cause:

- Kiwoom returned the trade as multiple same-symbol realized PnL rows, not one row for the full order quantity.
- The existing broker-day matcher handled exact single-row matches and same-price split rows, but not split rows where the final sell average must be matched by weighted average.
- Regeneration also dropped some order-status fill fields in the minimal execution rebuild path, reducing the evidence available for disambiguation.

Patch:

- Preserved order-status fill price and broker truth source during minimal execution rebuild.
- Added weighted split-fill matching for same-symbol `ka10077` rows using buy price, total quantity, and weighted sell average.
- Removed reverse-estimated realized PnL display from the summary path; final execution PnL, fee, and tax must come from broker truth when available.

Updated `TRD_20260506_018880_10` Truth Surface:

- buy/sell: `5,410 / 5,435`
- realized PnL: `-6,597 (-0.44%)`
- fee/tax: `10,410 / 2,987`
- price change: `+0.46%`
- cost drag: `13,397 (0.91%)`
- source: Kiwoom day realized PnL `ka10077`

Follow-up check:

- Scanned 2026-05-06 trade summaries after regeneration.
- No remaining `실현 손익: 확인 불가` or blank `수수료 / 세금: - / -` entries were found in completed summaries.

## Korea Market Index Context

Issue:

- Strategist input exposed US index moves and VIX, but KOSPI/KOSDAQ current index context was not visible as a structured market-state input.
- `market_context_inputs.index_trend` could remain a generic scalar with no operator-visible KOSPI/KOSDAQ basis.
- Trade summaries therefore could mention market state without showing the actual domestic index values used around entry.

Patch:

- Added Kiwoom market index reader for `ka20009`:
  - KOSPI: `inds_cd=001`
  - KOSDAQ: `inds_cd=101`
  - fields: current index, previous close, change, change pct, open/high/low, breadth counts, dates, source.
- Added request gap and retry handling for Kiwoom rate limit `1700` when reading both indices.
- Added domestic index evidence into `global_sentiment_signal`:
  - `index_moves.kospi_pct`
  - `index_moves.kosdaq_pct`
  - `korea_indices.indices.KOSPI`
  - `korea_indices.indices.KOSDAQ`
- Strategist now uses domestic index context as fallback market-state inputs:
  - `market_context_inputs.index_trend` from average KOSPI/KOSDAQ change pct, normalized by `/ 5`
  - `market_context_inputs.market_breadth` from KOSPI/KOSDAQ rising/falling/unchanged counts
- Strategist LLM compact payload, strategist event snapshots, and global sentiment breakdown now carry `korea_indices`.
- Trade report generation now preserves `korea_indices` into `market_context_at_entry`.
- `ai_trade_summary.md` market-state section now prints domestic index lines such as:
  - `국내 지수: KOSPI 현재 ... 전일 ... 등락률 ...`
  - `국내 지수: KOSDAQ 현재 ... 전일 ... 등락률 ...`

Validation:

- Kiwoom mock endpoint check succeeded for both KOSPI and KOSDAQ after request-gap patch.
- Current environment check: `KIWOOM_MODE=mock`.
- Added and passed tests for Kiwoom index parsing, global sentiment Korea index propagation, strategist market inputs, human market context, and trade summary rendering.

## Cost Patch Applicability Check

Issue:

- The previous cost-aware exit patch was present in the live artifacts, but today's trades still produced many gross-positive / net-negative exits.
- Evidence from `TRD_20260506_018880_10`:
  - exit trace showed `Cost-aware profit floor: 1.20% (round-trip cost 0.90% + buffer 0.30%)`.
  - the actual exit reason was `intraday_low_break`.
  - broker truth cost drag was about `0.91%`, while the trade's price move was about `+0.46%`, so the final result was still negative.
- Entry cost filter evidence from the same trade:
  - estimated round-trip cost: `3,141.6`
  - estimated cost drag: `0.21%`
  - estimated gross edge: `1.52%`
  - cost-adjusted edge: `1.31%`
  - result: `passed=true`
- Truth Surface later showed actual broker fee/tax cost drag near `0.90%`.

Finding:

- The patch did not disappear. It applied to profit-taking floors.
- It did not fully solve today's loss pattern because the runtime has two separate cost paths:
  - entry filter estimated cost using fee/tax rates around `0.21%`;
  - exit profit floor used a conservative `1.20%` floor;
  - Truth Surface showed actual mock broker drag around `0.80%~0.90%`.
- Protective exits such as `stop_loss`, `intraday_low_break`, and `vwap_breakdown` can still sell before net breakeven. That is sometimes correct risk control, but it means the cost patch cannot prevent all cost-drag losses.
- `peak_drawdown` and `trailing_stop` already avoid triggering on small positive profit below the floor, but `intraday_low_break` and `vwap_breakdown` are still allowed to cut the position even when gross PnL is positive but net PnL is not.

Patch Direction:

- Unify entry and exit cost assumptions.
  - Entry filter should use `effective_cost_drag_pct = max(estimated_fee_tax_drag, observed_or_configured_round_trip_floor)`.
  - Default floor should align with the existing exit floor base: `round_trip_cost_floor_pct=0.009`.
  - Keep a minimum net edge buffer, e.g. `0.003`, so entry requires at least about `1.20%` expected gross move before considering a trade.
- Replace the current quality-score-only gross edge estimate with a stricter expected-move estimate.
  - Use explicit target / resistance distance / ATR / recent realized move when available.
  - Treat quality score as a confidence modifier, not as the whole expected move.
- Add a protective-exit net-breakeven guard for soft defensive exits.
  - `intraday_low_break` and `vwap_breakdown` should distinguish hard invalidation from noise exit.
  - If current gross PnL is positive but below cost floor, only exit when a hard invalidation is confirmed; otherwise require confirmation ticks or hold.
- Add report counters:
  - `gross_positive_net_loss_count`
  - `protective_exit_below_breakeven_count`
  - `entry_cost_model_mismatch_count`
  - exit reason breakdown for cost-drag losses.

Decision:

- Next code patch should focus on cost-model unification first, then protective-exit breakeven behavior.
- Do not simply raise take-profit levels again; they are already cost-aware. The missing part is entry cost estimation and protective-exit behavior below breakeven.

Implemented Patch:

- Entry cost filter now computes:
  - `effective_cost_drag_pct = max(estimated_fee_tax_drag, round_trip_cost_floor_pct)`
  - default `round_trip_cost_floor_pct=0.009`
  - default `min_net_profit_buffer_pct=0.003`
  - default required gross edge around `1.20%`
- Entry cost filter output now records:
  - `effective_cost_drag_pct`
  - `cost_floor_applied`
  - `required_gross_edge_pct`
  - `estimated_gross_edge_source`
  - `expected_move_candidates`
  - `quality_proxy_edge_pct`
- Expected gross edge is no longer only a raw quality-score transform.
  - Explicit expected move / target / resistance / ATR / volatility inputs are preferred when available.
  - Quality score is used as a confidence modifier for explicit candidates.
  - If no explicit move is available, a capped quality proxy remains as fallback.
  - Plain recent/day/intraday high distance is not treated as a target because it over-blocked valid reclaim/breakout tests.
- Protective exits now distinguish net-breakeven state:
  - `vwap_breakdown` and `intraday_low_break` are blocked when current gross PnL is positive but below the cost-aware profit floor, unless a hard invalidation is confirmed.
  - Hard invalidation can come from explicit policy flags, chart structure breakdown, or a deeper-than-threshold VWAP/intraday-low break.
  - `hard_stop` and `stop_loss` remain immediate risk exits.
- Monitor/report surfaces now carry:
  - `protective_exit_floor_blocked`
  - `protective_exit_floor_blocked_reason`
  - `protective_exit_hard_invalidation`
  - `protective_exit_hard_invalidation_reason`

Validation:

- `tests/test_strategy_sizing_exit_upgrade.py tests/test_m29_3_monitor_exit_policy.py`: `40 passed`.
- Targeted monitor cost/entry/protective-exit path with `EXIT_POLICY_USE_EOD_FLAT=false`: `11 passed`.
- `py_compile` passed for `graphs/nodes/monitor_node.py` and `libs/runtime/exit_policy.py`.
- Note: full `test_monitor_exit_guard.py` was not used as the primary signal during the live afternoon window because current wall-clock closeout guard changes unrelated entry expectations to `buy_blocked_closeout_window`.

Restart:

- Old live loop stopped:
  - parent PID `18904`
  - lock owner PID `7492`
- New live loop started:
  - parent PID `8504`
  - lock owner PID `13132`
- Command:
  - `scripts/run_session.py --mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --session-hard-gate --allow-offhours`
- Watch after restart:
  - loop alive: `true`
  - event lag: `0s`
  - health: `YELLOW`
  - reason: `blocked_rate_high:100.00%`
  - broker failures: `0`
- Interpretation:
  - The process is running cleanly.
  - The yellow state is from recent `noop_intent_skipped` blocks in the 30-minute window near close, not from a process or broker failure.

## Validation

- Targeted runtime/report tests: passed.
- `tests/test_strategy_horizon_feedback.py`, `tests/test_trade_bundle_state.py`, `tests/test_trade_execution_snapshot.py`: passed.
- `tests/test_trade_report_ai.py`: passed.
- Split-fill broker truth tests: passed.
- Report/regeneration suite: `124 passed`.

Known unrelated local test issue:

- one `tests/test_execute_from_packet.py` case can fail in the local temp catalog setup with missing `.pytest-work/.../api_catalog.jsonl`; the patched price-source cases passed.

## Restart Need

Runtime code changed in the live SELL price path, so the live session should be restarted after this patch.

## Restart Result

- Old live session stopped: parent `10384`, child `6136`.
- New live session started: parent `8096`, loop/lock owner `16700`.
- Command: `scripts/run_session.py --mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --session-hard-gate --allow-offhours`
- Live watch status after restart: `GREEN`.
- 30-minute watch window: `785` events, `12/12` strategist LLM ok, `5` executions, broker failures `0`.

## Strategy Detail / Candidate Watch Plan

Documented the next strategist-output upgrade:

- New design doc: `docs/strategist_output/strategy_detail_candidate_watch_policy_2026-05-06.md`
- Scope:
  - separate `pre_llm_playbook`, `llm_requested_playbook`, and `final_playbook`
  - add `tactical_strategy`, `strategy_scores`, and `rejected_strategy_reasons`
  - add strategist-proposed `candidate_watch_policy`
  - let Commander clamp the proposal into final `entry_control`
  - let Scanner and Monitor use the final watch depth consistently
- Intended first implementation phase is visibility-only/additive before runtime behavior changes.

Implementation update:

- Phase 1 visibility-only code has been applied.
- `strategist_output` now records:
  - `pre_llm_playbook`
  - `llm_requested_playbook`
  - `requested_playbook`
  - `requested_playbook_source`
  - `final_playbook`
  - `tactical_strategy`
  - `strategy_scores`
  - `rejected_strategy_reasons`
  - `candidate_watch_policy`
- Existing `strategy_policy.market_policy` and `strategy_policy.scanner_policy` now carry the same visibility handoff fields without changing runtime behavior.
- `reports/llm/.../strategist/strategist_summary.md` now includes a `Strategy Detail` section.
- `ai_trade_report` compact input and `전략가 출력 근거` markdown now carry/render the same `strategy_detail` fields.
- `candidate_watch_policy.behavior_effect=visibility_only`; Commander/Scanner/Monitor execution behavior is intentionally unchanged in this patch.

Execution bridge update:

- Phase 2/3 execution bridge has been applied after the visibility patch.
- Strategist LLM output changes:
  - strategist prompt contract asks for `tactical_strategy`, `strategy_scores`, `rejected_strategy_reasons`, and `candidate_watch_policy`
  - strategist canonical output stores deterministic pre-LLM playbook, LLM requested playbook, and final playbook separately
- Reporter LLM input changes:
  - `ai_trade_report` compact input includes `strategy_detail`
  - markdown renders `전략가 출력 근거` with playbook flow, tactical strategy, strategy scores, and candidate watch proposal
- Execution behavior changes:
  - Commander consumes `candidate_watch_policy`
  - Commander writes final executable scope to `entry_control`
  - Scanner uses final `max_priority_rank` for `watch_candidates`
  - Monitor uses final `max_runner_ups`, `cascade_enabled`, `cascade_allowed_reasons`, and `cascade_blocked_reasons`
- Safety behavior:
  - no strategist proposal: existing baseline behavior remains unchanged
  - open position or preflight block: rank 1, runner-ups 0, cascade disabled
  - risk-off/defensive/degraded tape: max rank 3
  - neutral/balanced: max rank 7
  - risk-on/offensive: max rank 10

Validation:

- `py_compile`: passed for strategist node, strategist summary renderer, and related tests.
- `tests/test_strategist_llm_summary.py`, `tests/test_strategist_frame_llm_integration.py`, `tests/test_m21_commander_runtime_entry.py`: 109 passed.
- `tests/test_trade_report_ai.py`: 112 passed.
- `py_compile`: passed for Commander, Scanner, Monitor, and cascade plan modules.
- `tests/test_m21_commander_runtime_entry.py`, `tests/test_monitor_feedback_adaptive_policy.py`, `tests/test_monitor_candidate_cascade.py`: 81 passed.
- `tests/test_strategist_frame_llm_integration.py`, `tests/test_strategist_llm_summary.py`, `tests/test_trade_report_ai.py`: 150 passed.
- Monitor cascade regression subset: 3 passed.

Known unrelated local regression:

- Full `tests/test_monitor_exit_guard.py` has one existing cost-filter expectation mismatch:
  - `test_monitor_policy_aware_gating_can_promote_breakout_near_ready_reclaim`
  - observed block: `cost_adjusted_edge_not_ready`
  - this is outside the candidate watch bridge patch and should be handled in the cost-filter test alignment pass.

Reporting visibility update:

- Phase 4 reporting visibility has been applied.
- Monitor now records additional cascade details:
  - top-pick reason
  - runner-up rank and score
  - fallback rank
  - final selected symbol and rank
- `ai_trade_report` compact input now includes:
  - `entry_execution_visibility.strategy_candidate_watch_proposal`
  - `entry_execution_visibility.commander_entry_control`
  - `entry_execution_visibility.monitor_entry_candidate_cascade`
  - `commander.entry_control`
  - `monitor.entry_candidate_cascade`
- Full trade report and `ai_trade_summary.md` now show:
  - strategist candidate watch proposal
  - Commander final watch scope and clamp reason
  - whether Monitor attempted runner-up cascade
  - whether the final entry candidate switched from the top scanner pick to a runner-up

Validation:

- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q`: 114 passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_candidate_cascade.py tests\test_monitor_feedback_adaptive_policy.py -q`: 10 passed
- `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py tests\test_strategist_llm_summary.py -q`: 38 passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`: 71 passed
