# 2026-05-12 Scanner Macro Chart-Fit and Monitor Entry Quality

## Background

The scanner and monitor were both looking at chart context, but the boundary was not explicit enough:

- Scanner should rank candidates by the bigger chart context: trend alignment, relative strength, volume accumulation, breakout/base quality, and risk balance.
- Monitor should decide the live entry timing: VWAP reclaim/hold, candle quality, pullback/breakout readiness, cost-aware edge, and exit risk.

This patch keeps the strategist schema unchanged and uses the existing strategist fields (`playbook`, `scanner_priority`, `risk_tone`, `trade_aggressiveness`) to guide both layers.

## Runtime Changes

- Added `scanner_macro_chart_fit` as a separate scanner concept from the existing monitor-style `scanner_chart_fit`.
- Scanner macro chart-fit is a soft rank bias only.
  - It can lightly improve or reduce ranking.
  - It does not directly order or block trades.
  - It stays neutral when feature coverage is too thin.
- Scanner macro chart-fit components:
  - `trend_alignment_score`
  - `relative_strength_score`
  - `adx_trend_score`
  - `volume_accumulation_score`
  - `breakout_base_score`
  - `risk_balance_score`
  - `overextension_risk`
- Monitor human-chart setup now also checks:
  - last candle quality
  - VWAP reference quality
  - reward-room score
  - multi-window structure score
- These monitor quality checks can prevent a near-ready chart setup from being promoted from WAIT to BUY when the final candle is weak or the setup has poor reward/risk.

## Report and LLM Visibility

- Scanner outputs now include:
  - `scanner_macro_chart_fit_score`
  - `scanner_macro_chart_fit_bias`
  - `scanner_macro_chart_fit_authority`
  - `scanner_macro_chart_fit_components`
- Ranked candidates, scanner output, scanner selection reason, commander post-scanner compact context, and trade story input preserve the new macro chart-fit fields.
- Monitor outputs now include:
  - `human_chart_detail_context`
  - `human_candle_quality_score`
  - `human_vwap_reference_quality_score`
  - `human_reward_room_score`
  - `human_multi_window_structure_score`
- Monitor reason/report story bullets now surface:
  - candle shape: close location, upper wick, lower wick, body ratio
  - VWAP reference: source, bar count, explicit VWAP bar count, explicit ratio
  - reward room: nearby resistance and room/extension percentage

## Validation

- `venv\Scripts\python.exe -m py_compile graphs/nodes/scanner_node.py libs/runtime/intraday_monitor_signals.py graphs/commander_runtime.py libs/reporting/trade_story_pipeline.py`
- `venv\Scripts\python.exe -m pytest -q tests/test_intraday_monitor_signals.py`
- `venv\Scripts\python.exe -m pytest -q tests/test_scanner_strategy_frame_integration.py tests/test_scanner_monitor_compatibility.py`
- `venv\Scripts\python.exe -m pytest -q tests/test_commander_post_scanner_context.py`
- `venv\Scripts\python.exe -m pytest -q tests/test_trade_story_pipeline_enrichment.py`
- `venv\Scripts\python.exe -m pytest -q tests/test_m21_commander_runtime_entry.py`
- `venv\Scripts\python.exe -m pytest -q tests/test_trade_report_ai.py -k "trade_summary or horizon"`

Initial result:

- `tests/test_intraday_monitor_signals.py`: 69 passed
- `tests/test_scanner_strategy_frame_integration.py tests/test_scanner_monitor_compatibility.py tests/test_commander_post_scanner_context.py`: 91 passed
- `tests/test_trade_story_pipeline_enrichment.py`: 32 passed
- `tests/test_m21_commander_runtime_entry.py`: 81 passed
- `tests/test_trade_report_ai.py -k "trade_summary or horizon"`: 17 passed, 116 deselected
- `py_compile`: passed

## Live Check Items

- Confirm `scanner_macro_chart_fit_bias` is non-zero only when longer chart features are populated.
- Confirm the Stage 2 strategist context receives the macro chart-fit compact fields.
- Confirm monitor BUY promotions show candle/VWAP/reward-room details in monitor artifacts and trade story input.
- Confirm generated `ai_trade_summary.md` keeps the monitor story bullets visible in the entry section after a real BUY run.
- Watch whether the extra candle-quality check blocks obvious long upper-wick chase entries without starving valid pullback/reclaim entries.
