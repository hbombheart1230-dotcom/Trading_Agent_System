# 2026-05-14 Strategist LLM Token Budget

## Summary

- Reduced duplicated strategist LLM payload fields while preserving deterministic evidence.
- Added a stage-aware token budget policy to compact strategist payloads.
- Lowered the default refresh output cap from 4096 to 2048 tokens unless `STRATEGIST_REFRESH_MAX_TOKENS` overrides it.

## Changes

- Replaced full `theme_strength_packet` in the LLM payload with `theme_strength_packet_summary`.
- Kept compact `theme_strength` top scores instead of sending broad raw theme payloads.
- Trimmed `monitor_entry_policy_baseline` to fields the strategist can actually adjust.
- For selected-symbol, stale-hold, and end-of-day refresh calls:
  - removes raw market/candidate news samples from the prompt,
  - keeps only news counts and policy summary,
  - trims available theme component symbols,
  - trims scanner candidate context,
  - keeps only daily and symbol memory packets,
  - removes broad weekly/monthly memory packets from refresh prompts.

## Rationale

- Stage 1 market framing still receives broad market context.
- Stage 2/3/4 refresh calls are symbol/position-specific and should not resend the full Stage 1 context.
- This complements the existing strategist cache and the new input-fingerprint cache gate.

## Verification

- `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py::test_build_compact_strategist_llm_payload_trims_memory_and_news tests\test_strategist_frame_llm_integration.py::test_stage1_compact_payload_excludes_symbol_memory_until_selected_refresh tests\test_strategist_frame_llm_integration.py::test_compact_payload_resolves_stage3_and_stage4_call_kinds -q`
- `venv\Scripts\python.exe -m pytest tests\test_strategist_frame_llm_integration.py tests\test_operator_summary_memory_linkage.py tests\test_korea_market_indices_context.py tests\test_m21_commander_runtime_entry.py -q`

