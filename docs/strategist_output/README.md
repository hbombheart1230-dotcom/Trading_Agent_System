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

Theme source rule:

- strategist should expose `theme_strength_packet`, `theme_source`, and `theme_source_status`
- if Kiwoom theme data is unavailable, the report should distinguish source unavailability from a deliberate broad-market strategy
- scanner/report artifacts should show whether `sector_theme` candidates came from deterministic `theme_map/sector_map`

## Current Validation Status

As of `2026-04-28 12:38 KST`, the current live route is `SKIP_MONITOR_ONLY` because an open `000660` position exists. That means fresh `strategist.json` and `scanner.json` artifacts are not produced in the latest run.

Code/test verification is current for:

- structured strategist explanation contract
- Kiwoom theme packet and `selected_themes`
- news collection policy that reuses pre-scanner collected news instead of post-scanner re-querying
- memory and reporter-feedback visibility fields
- Commander-owned horizon handoff fields

Remaining live verification:

- next fresh strategist call must produce `selected_themes`, `theme_strength_packet`, `news_collection_policy`, `memory_usage_trace`, `reporter_feedback_packet`, and `commander_horizon_policy` in the same canonical artifact
- report rendering must continue to consume the structured strategist fields directly instead of reconstructing strategy rationale from prose

Cross-folder status:

- `docs/runtime_entrypoint/current_validation_status_2026-04-28.md`
