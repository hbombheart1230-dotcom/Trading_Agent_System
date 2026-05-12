# 2026-05-08 Post-Scanner Refresh Latency Fix

## Context

- Post-scanner refresh is required: scanner picks the concrete symbol, then strategist must rebuild the strategy frame for that selected symbol.
- Today the loop appeared to stop after scanner because post-scanner strategist refresh took several minutes.
- Evidence from `ff2124aafc234fe9a2f665bb932bb698`:
  - scanner/post-scanner phase started around `09:49:32~09:49:33`
  - strategist artifact was saved at `09:53:14`
  - prompt payload was about `67k` chars and prompt text about `80k` chars
- The biggest prompt contributors were:
  - `memory_packets`: about `26k` chars
  - `read_model_facts`: about `25k` chars
- Memory behavior is disabled/observability-only, but bulky memory/read-model facts were still being sent to the LLM prompt surface.

## Changes

- Keep post-scanner refresh enabled as the intended architecture.
- Compact strategist LLM prompt inputs:
  - `operator_summary` now keeps only metrics, conclusion, review points, and compact notes.
  - `read_model_facts.recent_trades` is limited to compact key fields for the latest 3 rows.
  - `read_model_facts.symbol_patterns` is limited to compact key fields for up to 5 symbols.
  - raw trade histories, raw rows, and large unneeded blobs are removed from LLM prompt input.
- For refresh calls, strategist `max_tokens` is capped at `4096` by default via `STRATEGIST_REFRESH_MAX_TOKENS` fallback logic.
- LLM call trace now records prompt and compact payload character counts for future latency diagnosis.
- Fixed post-scanner refresh symbol propagation:
  - Commander already carried `strategist_refresh_context.selected_symbol`.
  - Strategist LLM input incorrectly read only `open_position_refresh_context.selected_symbol`, so post-scanner refresh prompts could show an empty selected symbol.
  - The strategist now uses `strategist_refresh_context` when the refresh is post-scanner, and keeps `open_position_refresh_context` for holding-position refresh.
- Re-scoped the position-capacity direction to a minimal multi-position patch:
  - Do not pre-assign trades into `short_term` / `long_hold` slots for the next implementation.
  - Keep the current Strategist -> Scanner -> Monitor flow.
  - Let Strategist continue providing market-aware entry/exit strategy guidance.
  - Let Scanner and Monitor continue moving from that strategy frame.
  - Increase max active positions from 1 to a small number, starting with 3.
  - Keep existing overnight/carry policy.
  - Add only a strict same-symbol duplicate BUY block.
  - Treat the earlier two-slot documents as deferred design notes, not the active patch path.

## Result

- Same live prompt artifact recomputed through the patched compactor:
  - payload chars: `67257 -> 23579`
  - prompt chars: `80715 -> 33650`
  - memory packet surface: about `5138` chars
  - read model facts surface: about `3336` chars
- Live post-scanner refresh evidence after re-enable:
  - `a54ee116e94b4d3c9d994a2d09607c13` requested refresh for `selected_symbol_outside_cached_frame`.
  - Commander had selected symbol `078890`, but the LLM prompt still showed empty `selected_symbol`; this is the propagation bug fixed above.
- Live verification after the symbol propagation fix and restart:
  - `97212db2d60c432abd713f53aa417543`: refresh prompt selected symbol `018880`, trace selected symbol `018880`, selected-symbol memory `018880`.
  - `a17c3c79017549c69af8abae3ea0208f`: refresh prompt selected symbol `078890`, trace selected symbol `078890`, selected-symbol memory `078890`.
  - Refresh calls used `max_tokens=4096` with `refresh_token_cap_applied=true`.
- Minimal multi-position plan was documented in `docs/strategy_horizon_feedback/multi_position_minimal_patch_plan_2026-05-08.md`.
- Earlier two-slot documents were marked deferred:
  - `docs/strategy_horizon_feedback/horizon_slot_one_symbol_policy_2026-05-08.md`
  - `docs/strategy_horizon_feedback/horizon_slot_report_layout_2026-05-08.md`
  - `docs/strategy_horizon_feedback/two_slot_runtime_patch_plan_2026-05-08.md`
- `docs/strategy_horizon_feedback/README.md` was updated so the current policy is minimal multi-position, not two-slot.

## Verification

- `venv\Scripts\python.exe -m py_compile graphs\nodes\strategist_node.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_memory_linkage.py tests/test_strategist_frame_llm_integration.py::test_compact_strategist_llm_payload_limits_read_model_and_operator_summary_bulk tests/test_strategist_frame_llm_integration.py::test_build_strategist_llm_messages_enforces_read_model_facts_and_policy_adjustment tests/test_strategist_frame_llm_integration.py::test_build_strategist_llm_messages_disables_memory_usage_when_policy_disabled tests/test_strategist_frame_llm_integration.py::test_strategist_llm_payload_includes_commander_refresh_context tests/test_strategist_frame_llm_integration.py::test_strategist_refresh_uses_persisted_selected_symbol_memory_when_not_in_read_model_facts -q`
  - `8 passed`
- `venv\Scripts\python.exe -m pytest tests/test_strategist_frame_llm_integration.py tests/test_phase1_agent_artifact_quality.py tests/test_m21_commander_runtime_entry.py -q`
  - `129 passed`
- Runtime restarted with post-scanner refresh enabled:
  - command: `scripts\run_session.py --mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --session-hard-gate --allow-offhours`
  - lock owner after restart: PID `24388`

## Risk

- Strategy context is still present, but no longer includes full raw read-model/operator-summary detail.
- If future strategy work needs deeper memory evidence, it should add a small explicit field instead of re-expanding raw history into the live prompt.
- Refresh still depends on LLM provider latency. If prompt size is compact but latency remains high, the next fix should be a dedicated refresh-light contract/model path rather than disabling refresh.

## Update: 4-Stage LLM Artifact Boundary

### Context

- The 4-stage Strategist LLM design needs a runtime/reporting boundary before dedicated Stage 3/4 LLM calls are added.
- Existing reports and tests depend on `reports/llm/YYYY-MM-DD/<run_id>/strategist/`, so the legacy Strategist artifact path must remain stable.
- Stage 1 should not use symbol-specific memory. Stage 2 is where selected-symbol memory belongs because Scanner has already produced the concrete candidate.

### Changes

- Added run-level `llm_stage_manifest.json`.
- Added stage-specific Strategist LLM artifact names:
  - `strategist_stage1_market_frame`
  - `strategist_stage2_selected_symbol`
  - `strategist_stage3_hold_review`
  - `strategist_stage4_carry_review`
- Existing `strategist/` prompt, response, meta, and summary files remain the canonical operator-facing summary path.
- Strategist LLM calls now mirror their prompt/response/meta into the resolved stage-specific folder and upsert the manifest.
- Stage 1 compact payload now removes:
  - `read_model_facts.symbol_patterns`
  - `memory_packets.symbol_memory_packet`
  - `commander_refresh_context.selected_symbol_memory`
- Stage 2 post-scanner refresh now runs after Scanner selection when entry capacity exists and a selected symbol is present.
- Fresh Stage 1 flows only force Stage 2 when Scanner has actually selected a symbol. They do not re-trigger from stale pre-scanner `monitor_output` alone.
- Stage 3/4 manifest rows are recorded as `skipped` when no eligible review ran, without overwriting a real Stage 3/4 row if one already exists.

### Verification

- `python -m py_compile libs\runtime\canonical_artifacts.py graphs\nodes\strategist_node.py graphs\commander_runtime.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_canonical_artifact_validation.py tests\test_strategist_frame_llm_integration.py -q`
  - `46 passed`
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - `73 passed`

### Risk

- Stage 2 now adds an extra Strategist LLM call after eligible Scanner selections, so provider latency/cost can increase.
- Stage 3/4 are still manifest/skip tracked only; their dedicated LLM prompt/call behavior remains a separate implementation step.
- The existing `strategist_summary.md` remains stable, but it does not yet render the full four-stage manifest inline.

## Update: Stage 3/4 Strategist LLM Review Activation

### Context

- Stage 3 is the stale intraday hold review: when a held position repeats HOLD or hits loss/risk refresh criteria, Strategist should review whether to maintain, tighten, or exit.
- Stage 4 is the closeout/carry review: near session close, held positions need a distinct carry/overnight review before Monitor applies closeout behavior.
- Preopen carried-position risk is not Stage 4. It is position-risk review and should classify as Stage 3.

### Changes

- Tightened Strategist call-kind classification:
  - `open_position_monitor_refresh` -> `stale_intraday_hold_review`
  - `preopen_carry_risk_review` -> `stale_intraday_hold_review`
  - `session_closeout_carry_review` / `end_of_day_carry_review` -> `end_of_day_carry_review`
- Added Stage 4 carry-review context builder for closeout:
  - selected held symbol
  - position count
  - carry state/risk/reason
  - minutes to close
  - hold repeat/loss context
  - compact position list
- Session closeout guard now runs Stage 4 Strategist LLM before Monitor when there is a held position.
- Pending BUY cancel remains higher priority and still executes before Monitor/Stage4 position review.
- Default closeout phase now runs Stage 4 if held positions remain; otherwise it records skip state and stays `closeout_idle`.
- Stage 3/4 skip manifest rows still do not overwrite real Stage 3/4 LLM rows.

### Verification

- `python -m py_compile graphs\commander_runtime.py graphs\nodes\strategist_node.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
  - `74 passed`
- `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py tests\test_canonical_artifact_validation.py -q`
  - `47 passed`

### Risk

- Stage 4 adds another LLM call near close when positions remain. If provider latency is high, closeout timing should be watched closely.
- Stage 4 is advisory/policy refresh only. Hard closeout, broker truth, and risk controls remain outside LLM authority.
- Stage 3 is still cadence-triggered by existing repeated-hold/loss refresh logic; it does not run on every HOLD.

## Update: Entry Policy Guard

### Context

- Live monitor summaries around `11:38~11:40` showed `entry_thresholds.enabled=false` and `monitor_reason=intraday_entry_disabled`.
- The raw strategist LLM responses for the same window had `monitor_entry_policy.enabled=true`.
- This means the disable flag was introduced after the LLM response, in the commander-applied policy / cached strategy handoff path.
- Memory usage was also still partially visible to strategist prompts even when commander memory policy was disabled.

### Changes

- Commander now applies a flat/session guard: if there is no open position, the phase is `session`/`intraday`, and the normalized monitor entry policy is disabled, it forces entry policy back to enabled and records `flat_session_entry_policy_enabled_forced`.
- Strategist prompt generation now removes the remaining memory-sensitive user prompt directives when memory usage is disabled.
- Compact strategist payloads hide `read_model_facts`, recent strategy feedback, reporter feedback, strategy memory, and memory packets behind a disabled/audit-only stub.
- Monitor no-trade and entry-blocker surfaces now expose:
  - `confidence_gap`
  - `confidence_near_miss`
  - `near_ready_reasons`
  - `entry_probe_candidate`

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py graphs\nodes\strategist_node.py libs\runtime\decision_observability.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_decision_observability.py tests\test_m21_commander_runtime_entry.py tests\test_strategist_frame_llm_integration.py -q`
  - `114 passed`
- Direct smoke check:
  - flat/session applied policy forced `enabled=True`
  - override reason: `flat_session_entry_policy_enabled_forced`
  - memory-disabled compact payload returned `visible_to_llm=False`
  - old user prompt rule `Do not ignore repeated patterns across memory packets` was absent in disabled mode
- Runtime restarted after stale lock cleanup:
  - live loop PID: `1416`
  - parent PID: `19220`
- Live verification after restart:
  - `intraday_entry_disabled` after restart: `0`
  - latest monitor summary: `entry_thresholds.enabled=true`
  - latest no-trade reason: `pullback_not_mature`
  - latest confidence: `0.5489`
  - latest confidence gap to `0.55`: `0.0011`
  - latest `confidence_near_miss=true`

### Risk

- This guard is intentionally narrow: it only forces entry enabled when flat and in session/intraday. It should not override closeout, open-position, risk, or broker truth blocks.
- It does not force a buy. The current live blocker moved from policy-disabled to normal entry-quality gating, mainly pullback maturity and confidence threshold near-miss.

## Update: Candidate Cascade And Cost Proxy

### Context

- Even after entry policy was re-enabled, live trading remained near zero.
- Today strategist outputs were almost all `pullback / leader_vwap_reclaim_pullback`.
- Strategist commonly proposed `rank<=5 / runner_ups=4 / cascade=true`, and Commander sometimes expanded to `rank<=10 / runner_ups=9`.
- Actual monitor summaries showed many cycles still only evaluated rank #1 because cascade was not eligible for common blockers:
  - `pullback_not_mature`
  - `volume_confirmation_missing`
- BUY-ready cases also hit `cost_adjusted_edge_not_ready` because directional expected edge was missing even when ATR/volatility proxy evidence was present.

### Changes

- Added `pullback_not_mature` and `volume_confirmation_missing` to default cascade-eligible reasons.
- Updated strategist LLM contract and sanitizer so future `candidate_watch_policy.cascade_allowed_reasons` can include those reasons.
- Updated Commander candidate-watch proposal normalization to merge default allowed/blocked reasons with the strategist proposal. This prevents stale cached LLM policy from accidentally dropping new required cascade reasons.
- Added narrow cost-filter proxy support:
  - only when `entry_info.triggered=true`
  - confidence is at or above threshold
  - ATR/range/volatility proxy evidence exists
  - proxy quality check passes
  - cost-adjusted edge still clears cost floor and minimum edge
- Added observability fields:
  - `effective_directional_edge_required`
  - `effective_proxy_edge_allowed`
  - `triggered_signal_proxy_edge_allowed`
  - `allow_triggered_signal_proxy_edge`

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py graphs\nodes\monitor_node.py graphs\nodes\strategist_node.py libs\runtime\monitor_candidate_cascade.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_monitor_candidate_cascade.py tests\test_monitor_exit_guard.py::test_entry_cost_filter_rejects_volatility_proxy_without_directional_edge tests\test_monitor_exit_guard.py::test_entry_cost_filter_allows_triggered_signal_volatility_proxy -q`
  - `6 passed`
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_intraday_monitor_signals.py tests\test_monitor_candidate_cascade.py tests\test_monitor_exit_guard.py::test_monitor_blocks_buy_when_cost_adjusted_edge_is_not_enough tests\test_monitor_exit_guard.py::test_entry_cost_filter_rejects_volatility_proxy_without_directional_edge tests\test_monitor_exit_guard.py::test_entry_cost_filter_allows_triggered_signal_volatility_proxy -q`
  - `142 passed`
- After Commander default-merge patch:
  - `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_monitor_candidate_cascade.py tests\test_monitor_exit_guard.py::test_entry_cost_filter_rejects_volatility_proxy_without_directional_edge tests\test_monitor_exit_guard.py::test_entry_cost_filter_allows_triggered_signal_volatility_proxy -q`
  - `78 passed`
- Live restart result:
  - restarted loop PID `560`, then final merged-policy restart PID `10948`
  - `live_watch` status GREEN
  - recent execution: BUY 1, broker success 1, broker code `0`
  - BUY evidence: `005930`, fallback from cascade, cost filter passed with `edge_evidence_type=proxy`, `triggered_signal_proxy_edge_allowed=true`, estimated gross edge `0.013389`, cost-adjusted edge `0.004389`

### Risk

- This does not allow proxy edge for ordinary NOOPs. It only applies after monitor has already produced a BUY-ready signal.
- Open-position guard still prevents duplicate buys after a position is held.
- The patch increases trading frequency from zero, so live validation should watch whether proxy-edge buys still clear round-trip costs after fills and tax.

## Update: Minimal Multi-Position Runtime Patch

### Context

- The two-slot short/long design is deferred.
- The active direction is a smaller runtime patch:
  - keep the current Strategist -> Scanner -> Monitor flow
  - allow more than one distinct held symbol
  - block duplicate BUYs for the same symbol
  - keep existing overnight/carry and closeout policy

### Changes

- Commander now resolves `RISK_MAX_POSITIONS` and publishes a thin multi-position policy:
  - `enabled=true` when max positions is greater than 1
  - `max_positions`
  - `same_symbol_reentry_allowed=false`
  - `pending_buy_same_symbol_allowed=false`
  - `open_position_gate_mode=max_positions`
- Commander no longer turns the runtime into monitor-only mode just because one position exists when capacity remains.
- Post-scanner/pre-buy strategist refresh can still run while positions exist if open position count is below max positions.
- Monitor entry guard now separates:
  - max-position reached
  - selected symbol already held
  - selected symbol pending BUY
- Candidate cascade can skip a held or pending top candidate and evaluate runner-ups when capacity remains.
- Exit priority is preserved: an active SELL signal still overrides fresh BUY intent.
- Local runtime config was changed to `RISK_MAX_POSITIONS=3`.

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py graphs\nodes\monitor_node.py libs\runtime\monitor_candidate_cascade.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_monitor_exit_guard.py tests\test_monitor_candidate_cascade.py tests\test_order_client.py tests\test_execute_from_packet.py tests\test_intraday_monitor_signals.py tests\test_phase1_agent_artifact_quality.py tests\test_m29_3_monitor_exit_policy.py -q`
  - `305 passed`

### Risk

- The runtime still emits at most one order intent per tick. This is intentional for the first multi-position patch.
- Live validation must confirm that broker truth, reports, and closeout remain coherent with 2-3 simultaneous positions.
- Same-symbol scaling remains disabled. If scaling is needed later, it should be a separate policy with explicit lot attribution.

## Update: BUY Order Price Propagation Fix

### Context

- Live run selected `078890` and the monitor BUY signal had valid market price evidence:
  - current price `8,850`
  - quantity `338`
  - estimated notional `2,991,300`
  - entry cost filter passed
- Executor still blocked the order with `order_notional_price_missing` because the BUY intent packet arrived without a usable top-level `price`.

### Changes

- Monitor BUY intents now publish an explicit order price from the best available entry evidence:
  - `entry_cost_filter.price`
  - selected candidate price
  - entry metrics current price
  - sizing price
- Monitor meta now records `price`, `current_price`, `price_source`, and `order_price_source` for the same resolved value.
- Commander runtime now has a defensive fallback when a monitor BUY intent is missing top-level price:
  - intent meta price fields
  - nested `entry_cost_filter.price`
  - nested `entry_metrics.current_price`
  - monitor entry/output prices
  - market snapshot price as final fallback

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py graphs\nodes\monitor_node.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py tests\test_monitor_exit_guard.py tests\test_execute_from_packet.py tests\test_monitor_candidate_cascade.py -q`
  - `204 passed`

### Risk

- This does not loosen entry gates. It only prevents a valid monitor BUY signal from being dropped because the order packet lacked a propagated price.
- Live validation should confirm the next BUY reaches executor with a non-zero order price and no `order_notional_price_missing` block.

## Update: Closeout Broker Truth And Residual Position Reporting

### Context

- After closeout, the account still held two symbols: `005930` and `078890`.
- `005930` had an explicit `carry_overnight_approved` decision, but the daily report did not show the carry reason.
- `078890` was marked locally as flattened by closeout backup even though the Kiwoom mock account still showed `338` shares.

### Changes

- Closeout backup now treats `KIWOOM_MODE=mock` + `EXECUTION_MODE=real` as broker-truth-authoritative.
- In that mode, backup liquidation no longer removes a symbol from local state unless broker truth shows it is gone.
- If a non-carry symbol remains in the account, it is retained in `mock_positions`, marked as `unresolved_flatten_symbols`, and the closeout step returns a failure instead of hiding the exposure.
- Daily operator summary now includes `장마감 잔여 보유 종목`:
  - symbol
  - qty
  - avg/current price
  - account PnL ratio
  - overnight status
  - overnight reason and positive signals
- `daily_report.md` rendering also has the same residual-position section for future generation.
- Current state was reconciled to broker truth:
  - `005930`: overnight approved
  - `078890`: unresolved residual position, needs next-session action

### Verification

- `venv\Scripts\python.exe -m py_compile scripts\run_mock_exam_day.py libs\reporting\operator_period_summary.py scripts\generate_daily_report.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_run_mock_exam_day.py::test_closeout_backup_liquidation_flattens_mock_positions tests/test_run_mock_exam_day.py::test_closeout_backup_liquidation_respects_overnight_carry tests/test_run_mock_exam_day.py::test_closeout_backup_liquidation_keeps_broker_truth_unresolved_positions -q`
  - `3 passed`
- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py::test_operator_daily_summary_surfaces_residual_positions_and_overnight_reason tests/test_operator_summary_reports.py::test_operator_daily_summary_marks_runtime_activity_unavailable -q`
  - `2 passed`
- `venv\Scripts\python.exe -m pytest tests/test_daily_report.py::test_generate_daily_report_surfaces_residual_positions -q`
  - `1 passed`

### Risk

- Full `scripts\generate_daily_report.py` for `2026-05-08` did not complete within 10 minutes. The operator daily summary path was regenerated successfully, and the generator code is patched, but the full daily-report generation path needs a separate performance fix.

## Update: Friday Weekend Carry Guard

### Context

- `2026-05-08` is Friday KST.
- A Friday closeout carry is not ordinary overnight exposure; it is weekend exposure with a multi-day gap risk.
- The previous `carry_overnight_approved` path did not consider weekday/weekend risk.

### Changes

- Monitor carry evaluation now builds a carry calendar context from runtime clock fields.
- If the EOD carry decision happens on Friday, it marks:
  - `weekend_carry=true`
  - `holding_gap_days=3`
  - `carry_calendar.reason=friday_weekend_gap`
- Weekend carry is blocked by default with `weekend_carry_not_allowed:friday`.
- Weekend carry can only be considered if an explicit policy field allows it, and then it must clear stricter weekend buffers:
  - positive PnL buffer
  - trend-strength buffer
  - VWAP buffer
- Residual-position reports now label Friday-approved carry as `주말 오버나이트 승인(주의)` and print the weekend warning.

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py libs\reporting\operator_period_summary.py scripts\generate_daily_report.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests/test_monitor_exit_guard.py::test_monitor_can_approve_overnight_carry_near_close tests/test_monitor_exit_guard.py::test_monitor_blocks_default_weekend_carry_on_friday tests/test_monitor_exit_guard.py::test_monitor_flattens_near_close_when_overnight_carry_is_not_approved -q`
  - `3 passed`
- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py::test_operator_daily_summary_surfaces_residual_positions_and_overnight_reason tests/test_daily_report.py::test_generate_daily_report_surfaces_residual_positions -q`
  - `2 passed`

## Update: Strategist 4-Stage LLM Flow Draft

### Context

- The existing Strategist prompt mixes several concepts inside one `strategic_frame` call.
- Operator-facing discussion needs a clearer split:
  - 1차: market strategy frame
  - 2차: selected-symbol tactical refresh after Scanner
  - 3차: stale intraday hold review when a position is held too long
  - 4차: 15:20 end-of-day carry/overnight review

### Documentation

- Added `docs/strategy_horizon_feedback/strategist_4stage_llm_flow_draft_2026-05-08.md`.
- Updated `docs/strategy_horizon_feedback/README.md`.

### Key Decision

- 3차 is not the overnight decision.
- 3차 reviews whether an already-held intraday position has become stale and should be held, tightened, or exited.
- 4차 is the separate closeout/overnight carry decision near the end of the session.
- The main reason for 2차 is selected-symbol memory:
  - Stage 1 keeps the broad market frame.
  - Stage 2 re-checks Scanner's selected symbol using `symbol_memory_packet`.
  - Stage 2 output must separate live chart evidence from memory evidence.
- Added simple guard fields to the 4-stage draft:
  - `evidence_confidence`
  - `data_quality`
  - `commander_actionability`
- Additional buy / scale-in review is deferred as a separate future policy, not part of the current 3차 stale-hold review.

## Update: Slot Design Clarification

### Context

- The 1차/2차/3차/4차 Strategist discussion can be confused with the earlier 4-slot / 2-slot position designs.
- The active runtime path must stay unambiguous.

### Decision

- The earlier four-slot strategy design is HOLD / deferred.
- The earlier two-slot short/long design is HOLD / deferred.
- The current live path is not slot-based.
- The current live path keeps the existing Strategist -> Scanner -> Monitor flow with small multi-position capacity and duplicate same-symbol BUY blocking.
- The 1차/2차/3차/4차 language means Strategist LLM review stages, not position slots.
- Runtime-facing active-path JSON should use `remaining_position_capacity`, not `remaining_position_slots`.

### Documentation

- Updated `docs/strategy_horizon_feedback/README.md`.
- Updated `docs/strategy_horizon_feedback/strategist_4stage_llm_flow_draft_2026-05-08.md`.
- Updated `docs/strategy_horizon_feedback/strategist_4stage_chat_prompt_templates_2026-05-08.md`.
- Marked the deferred slot documents more explicitly as HOLD/deferred:
  - `docs/strategy_horizon_feedback/horizon_slot_one_symbol_policy_2026-05-08.md`
  - `docs/strategy_horizon_feedback/horizon_slot_report_layout_2026-05-08.md`
  - `docs/strategy_horizon_feedback/two_slot_runtime_patch_plan_2026-05-08.md`

## Update: Stage 2 Selected-Symbol Memory Contract

### Context

- The main reason for Stage 2 is not generic refresh; it is selected-symbol memory.
- Stage 1 should remain a broad market frame and should not pick the final stock.
- Scanner is the first component that creates the concrete ranked candidate set for the current cycle.
- If Stage 2 is only conditional, the runtime can enter a symbol without comparing that symbol against its own historical memory.

### Documentation

- Updated `docs/strategy_horizon_feedback/strategist_4stage_llm_flow_draft_2026-05-08.md`.
- Updated `docs/strategy_horizon_feedback/strategist_4stage_chat_prompt_templates_2026-05-08.md`.
- Updated `docs/strategy_horizon_feedback/README.md`.

### Decision

- Target Stage 2 becomes the default post-Scanner selected-symbol memory check.
- Eligible same-cycle flow:
  - Stage 1 market frame
  - Scanner ranked candidates
  - Commander packages Stage 2 input
  - Stage 2 selected-symbol tactical refresh
  - Commander clamps policy delta
  - Monitor calculates entry/hold/runner-up cascade
- Commander still owns the Stage 2 boundary, but its role changes:
  - guarantee Stage 2 when eligible
  - package selected-symbol memory
  - attach memory confidence and data-quality status
  - include runner-up memory only in compressed form
  - clamp Strategist output to allowed policy fields
  - keep hard risk controls outside LLM authority

### Guardrails

- Stage 2 output is not a direct order.
- LLM may recommend `watch`, `avoid`, `watch_with_tighter_gates`, or `cascade_to_runner_ups`.
- Commander decides whether `avoid` becomes a hard block or only tighter gates.
- Commander enforces cost hurdle, duplicate same-symbol guard, max position count, closeout window, order notional, and loss controls.
- Memory evidence may tighten, warn, or prioritize, but cannot alone force a BUY.

## Update: Stage 1 Memory Boundary and Stage 3/4 Conditional LLM Rules

### Context

- Stage 2 will use selected-symbol memory, so Stage 1 must stay clean as a broad market frame.
- Current Strategist payload paths can expose memory fields in the single `strategic_frame` call, even if live defaults often disable them.
- Stage 3 and Stage 4 should not become expensive every-cycle LLM calls.

### Documentation

- Updated `docs/strategy_horizon_feedback/strategist_4stage_llm_flow_draft_2026-05-08.md`.
- Updated `docs/strategy_horizon_feedback/strategist_4stage_chat_prompt_templates_2026-05-08.md`.
- Updated `docs/strategy_horizon_feedback/README.md`.

### Decisions

- Stage 1 must not consume:
  - `selected_symbol_memory`
  - `memory_packets.symbol_memory_packet`
  - `read_model_facts.symbol_patterns`
  - same-symbol win/loss history
  - symbol-specific blocker history
- Stage 2 is the first stage that may use selected-symbol memory.
- Stage 3 may use only the currently held symbol's thesis, position state, and relevant memory excerpt.
- Stage 4 may use held-symbol memory only as close/carry risk evidence.

### Stage 3 Scheduling

- Stage 3 is conditional and should be driven by a persisted review artifact, not only by raw HOLD count.
- The artifact records:
  - symbol
  - entry epoch
  - strategy horizon
  - entry thesis
  - expected hold window
  - first review time
  - review cadence
  - next review epoch
  - review triggers
  - last review result
- Monitor continues calculating every cycle.
- Commander calls Stage 3 only when the artifact is due or urgent review triggers appear.
- Hard deterministic exits do not wait for Stage 3.

### Stage 4 Gate

- Stage 4 is conditional and should run only near the closeout/carry window.
- It should be skipped when:
  - no position is held
  - hard flat policy already decides the result
  - hard stop/loss/liquidity rules already require exit
  - weekend/holiday carry is disallowed
  - deterministic carry minimums fail
- LLM may explain overnight risk, but cannot bypass Commander/Monitor hard carry guards.

## Update: Expected Exit Price Cost-Floor Guard

### Context

- Recent cost-aware exit work checked the profit floor against the monitor-observed current price.
- That was not enough when the actual sell fill could be lower than the observed/current price.
- Small gross-profit exits could still become net losses after fee/tax/slippage, even if the monitor snapshot looked positive.

### Changes

- Exit policy now computes an expected sell execution price before allowing profit-style exits.
- Expected exit price source priority:
  - best bid / bid from market quote when available
  - explicit `sell_slippage_buffer_pct` fallback when no bid is available
  - observed exit price only when no execution-discount evidence is provided
- Profit-style exits now require the expected execution price to clear the cost-aware floor:
  - `take_profit`
  - `opening_gap_profit_take`
  - `volume_exhaustion_take_profit`
  - `partial_take_profit`
  - `profit_ladder`
  - `risk_reward_take_profit`
  - `resistance_take_profit`
  - `vwap_extension_take_profit`
  - `time_decay_profit_exit`
- Stop-loss and risk exits are not blocked by this profit floor.
- Monitor now passes quote/bid evidence into exit policy when available.
- Monitor/report surfaces now include:
  - `expected_exit_price`
  - `expected_exit_price_source`
  - `expected_exit_pnl_ratio`
  - `expected_exit_net_pnl_ratio`
  - `expected_exit_profit_floor_met`
  - `expected_exit_profit_floor_blocked`
  - `expected_exit_profit_floor_blocked_reason`
- Trade report summary adds a compact expected-exit cost check when these fields are present.

### Guardrail

- There is no hidden default slippage penalty applied to every symbol.
- If a live best bid is available, it is used automatically.
- If no best bid is available, slippage fallback is used only when `sell_slippage_buffer_pct` is explicitly provided by policy/config.
- This prevents the new guard from broadly changing existing monitor behavior in quote-poor tests or runtime states.

### Verification

- `venv\Scripts\python.exe -m pytest tests\test_m29_3_monitor_exit_policy.py tests\test_monitor_exit_guard.py -q`
  - `113 passed`
- `venv\Scripts\python.exe -m py_compile libs\runtime\exit_policy.py graphs\nodes\monitor_node.py libs\reporting\trade_report_markdown_clean.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q -k "cost or fee or tax or drag or profit_floor or stop_loss or same_price or broker_pct or zero_price"`
  - `4 passed, 119 deselected`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py::test_render_trade_report_markdown_explains_same_price_round_trip_as_cost_loss tests\test_trade_report_ai.py::test_trade_summary_cost_analysis_keeps_zero_price_move_when_qty_missing tests\test_trade_report_ai.py::test_trade_summary_separates_broker_pct_from_notional_return_and_mock_cost_drag -q`
  - `3 passed`

### Live Check

- Watch whether profitable-looking exits now show `expected_exit_net_pnl_ratio` above the required floor before SELL.
- If reports still show small gross-profit exits becoming net losses, the next check should be whether live quote/bid data is missing from the monitor state.

## Update: 4-Stage Strategist LLM Contract Alignment

### Context

- `docs/strategy_horizon_feedback/strategist_4stage_chat_prompt_templates_2026-05-08.md` defines four Strategist LLM review stages.
- The runtime already had stage routing and artifact boundaries, but the LLM prompt still mostly used the old common `strategic_frame` output contract.
- This meant Stage 2/3/4 were labeled correctly, but the requested JSON fields did not fully match the document.

### Changes

- Strategist LLM prompt generation now switches the JSON contract by resolved stage:
  - Stage 1 `market_strategy_frame`
  - Stage 2 `selected_symbol_tactical_refresh`
  - Stage 3 `stale_intraday_hold_review`
  - Stage 4 `end_of_day_carry_review`
- Stage 2 prompt now requests the documented selected-symbol fields:
  - `selected_symbol_decision`
  - `target_symbol`
  - `target_rank`
  - `runner_up_order`
  - `monitor_instruction`
  - `entry_policy_delta`
  - `memory_usage`
  - `commander_actionability`
  - `confidence`
  - `reason`
- Stage 3 prompt now requests:
  - `hold_review_decision`
  - `exit_pressure`
  - `thesis_status`
  - `monitor_adjustment`
  - `priority_exit_triggers`
  - `next_check_minutes`
  - `reason`
- Stage 4 prompt now requests:
  - `carry_review`
  - `portfolio_level_decision`
  - `risk_note`
- Stage-specific outputs are preserved in `strategist_output`:
  - `selected_symbol_tactical_review`
  - `stale_intraday_hold_review`
  - `end_of_day_carry_review`
- Stage 2 output is safely mapped into the existing runtime surface:
  - `cascade_to_runner_up` becomes a bounded `candidate_watch_policy`
  - tighter-gate recommendations become `strategy_adjustment_directives`
  - no direct BUY/SELL authority is granted to the LLM
- Stage 3/4 outputs are advisory/policy-refresh surfaces only.
  - Monitor and Commander still own deterministic exits, closeout, weekend carry guard, broker truth, and risk controls.
- Stage-specific artifact refs are now exposed in `state["strategist_llm"]`:
  - `llm_stage_component`
  - `llm_stage_index`
  - `llm_stage_name`
  - `llm_call_kind`
  - `stage_prompt_ref`
  - `stage_response_ref`
  - `stage_meta_ref`
  - `llm_stage_manifest_ref`

### Verification

- `venv\Scripts\python.exe -m py_compile graphs\nodes\strategist_node.py`
  - passed
- `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py::test_stage_specific_llm_messages_match_4stage_contracts tests\test_strategist_frame_llm_integration.py::test_stage2_selected_symbol_contract_is_preserved_and_mapped_to_watch_policy -q`
  - `2 passed`
- `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py -q`
  - `40 passed`
- `venv\Scripts\python.exe -m pytest tests\test_canonical_artifact_validation.py tests\test_m21_commander_runtime_entry.py::test_m21_integrated_chain_closeout_guard_runs_stage4_carry_review_for_held_position tests\test_m21_commander_runtime_entry.py::test_m31_integrated_chain_reuses_cache_for_ten_minutes_by_default_when_commander_skip -q`
  - `11 passed`

### Risk

- Stage 2 can increase candidate cascade breadth when the LLM explicitly recommends `cascade_to_runner_up`.
- This still does not bypass cost hurdle, duplicate symbol guard, max-position guard, closeout guard, or broker truth.
- Stage 3/4 dedicated outputs are now stored and visible, but only conservative advisory mapping is applied. Direct LLM-driven liquidation/carry approval remains intentionally blocked.
