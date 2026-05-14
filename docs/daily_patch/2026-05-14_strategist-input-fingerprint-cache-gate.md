# 2026-05-14 Strategist Input Fingerprint Cache Gate

## Summary

- Reused the existing `persisted_state["strategist_output_cache"]` mechanism.
- Added a structured `input_fingerprint` to the cached strategist output.
- Commander now suppresses strategist refresh calls when the current scanner/monitor input context is materially unchanged from the cached frame.

## Fingerprint Inputs

- selected symbol
- selected rank bucket
- selected score bucket
- selected chart-fit bucket
- selected edge bucket
- entry gate bucket
- scanner top symbols
- top themes
- market regime
- open position count and symbols

## Behavior

- If the fingerprint is comparable and the drift score is below the material-change threshold, commander reuses the cached strategist frame.
- If selected symbol, top candidates, theme, market regime, entry quality, or position state changes enough, commander still allows strategist refresh.
- Post-scanner tactical refresh is also gated, so scanner can run with a cached frame without automatically forcing a second strategist LLM call.

## Verification

- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q`
- `venv\Scripts\python.exe -m pytest tests\test_m13_live_loop.py tests\test_m21_commander_runtime_entry.py tests\test_m22_skill_native_scanner_monitor.py -q`

