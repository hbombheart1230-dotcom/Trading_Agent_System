# Strategist Output

This folder documents the strategist output contract.

The strategist does not select the final trading symbol and does not place orders. Its job is to build the strategy frame used by downstream agents:

- market/regime interpretation
- risk posture
- playbook selection
- scanner ranking guidance
- monitor entry/hold/exit guidance
- explicit interpretation of memory and news inputs

Current contract draft:

- `strategist_explanation_contract_2026-04-25.md`
- `../kiwoom_truth/kiwoom_theme_strength_packet_2026-04-27.md`
- `news_query_target_flow_2026-04-28.md`
- `strategist_llm_summary_artifact_2026-04-28.md`
- `strategy_detail_candidate_watch_policy_2026-05-06.md`

## Design Principle

Strategist explanations must be stored as structured JSON first, then rendered into human text by reports and operator UI.

Free-text summaries are useful for operators, but they are not enough for runtime debugging. Every important explanation should also carry:

- source inputs
- whether it was used or ignored
- effect on strategy frame
- downstream handoff target
- reason and confidence

Reporter consumption rule:

- reports should use the structured strategist explanation fields as the primary source
- reports may render or shorten them for readability
- reports should not reconstruct a different strategist rationale when the strategist fields are present

Strategist LLM summary rule:

- `reports/llm/<day>/<run_id>/strategist/strategist_summary.md` is a deterministic render of the existing strategist `response.json`
- the summary must show strategist-authored interpretation first
- deterministic operator audit must be separated from strategist-authored interpretation
- the summary generator must not call another LLM or add new strategic rationale

Theme source rule:

- strategist should expose `theme_strength_packet`, `theme_source`, and `theme_source_status`
- if Kiwoom theme data is unavailable, the report should distinguish source unavailability from a deliberate broad-market strategy
- scanner/report artifacts should show whether `sector_theme` candidates came from deterministic `theme_map/sector_map`

Playbook diversity rule:

- strategist must provide a structured reason when it selects `defensive`
- neutral-market operation should not collapse into `defensive` by default
- when market regime, theme strength, liquidity, and volume quality are supportive, strategist should allow `breakout` or `momentum_pullback` frames
- memory-derived recent losses should distinguish entry-signal failure from cost/exit failure before forcing a more defensive playbook
- fresh strategist artifacts should expose why the chosen playbook was selected and which alternative playbooks were rejected
- strategist should propose candidate watch depth through `candidate_watch_policy`; Commander owns the final executable `entry_control`
- reports should show `pre_llm_playbook`, `llm_requested_playbook`, and `final_playbook` separately; Phase 1 visibility fields were implemented on `2026-05-06`
- reports should show the full candidate-watch chain: strategist proposal, Commander clamp/final scope, and Monitor cascade/fallback result

## Current Validation Status

As of `2026-04-28 closeout KST`, code/test verification is current for the strategist explanation contract and the new strategist LLM summary artifact.

Code/test verification is current for:

- structured strategist explanation contract
- Kiwoom theme packet and `selected_themes`
- news collection policy that reuses pre-scanner collected news instead of post-scanner re-querying
- memory and reporter-feedback visibility fields
- Commander-owned horizon handoff fields
- deterministic `strategist_summary.md/json` generation from strategist `response.json`
- `ai_trade_report` compact input and markdown rendering that consume structured strategist fields directly
- Phase 1 strategy detail visibility fields: `pre_llm_playbook`, `llm_requested_playbook`, `final_playbook`, `tactical_strategy`, `strategy_scores`, `rejected_strategy_reasons`, and proposed `candidate_watch_policy`
- Phase 4 candidate-watch reporting visibility: `entry_execution_visibility`, `commander.entry_control`, and `monitor.entry_candidate_cascade`

Remaining live verification:

- next fresh strategist call must produce `selected_themes`, `theme_strength_packet`, `news_collection_policy`, `memory_usage_trace`, `reporter_feedback_packet`, and `commander_horizon_policy` in the same canonical artifact
- report rendering must continue to consume the structured strategist fields directly instead of reconstructing strategy rationale from prose
- next generated `strategist_summary.md` should show real Kiwoom-selected themes instead of `theme=none / mode=fallback` when `available_themes` is present
- next live validation should check playbook concentration. If `defensive` dominates fresh frames in neutral conditions, strategist must record the explicit blocker that prevented `breakout` or `momentum_pullback`.

Cross-folder status:

- `docs/runtime_entrypoint/current_validation_status_2026-04-28.md`
- `docs/runtime_entrypoint/strategy_conservatism_review_2026-04-29.md`
