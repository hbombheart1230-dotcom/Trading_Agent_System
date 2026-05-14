# 2026-05-13 Trade Summary Entry and Exit Evidence Lines

## Background

The trade summary entry/exit sections were still too abstract:

- Entry showed a reason such as "VWAP hold + volume confirmed breakout" but did not always show the supporting values nearby.
- Exit showed "trend breakdown" but did not explain which trend metric breached which floor.

## Changes

- Entry judgment now surfaces monitor entry evidence lines when available:
  - current price, VWAP, VWAP distance and allowed band
  - volume ratio and minimum volume ratio
  - recent high and breakout level
  - confidence score and threshold
  - candle quality, VWAP reference quality, reward room score, multi-window structure score
  - candle shape: close location, upper wick, lower wick, body ratio
  - VWAP basis: source, minute bar count, explicit VWAP count, explicit ratio
  - upside room: nearby resistance, room to resistance, breakout extension
- Trend-breakdown exits now show a one-line basis:
  - `trend_strength`
  - `trend_strength_floor`
  - metric source when captured

## Validation

- `venv\Scripts\python.exe -m py_compile libs/reporting/trade_report_markdown_clean.py`
- `venv\Scripts\python.exe -m pytest -q tests/test_trade_report_ai.py -k "entry_vwap_volume or trend_breakdown_basis"`
- `venv\Scripts\python.exe -m pytest -q tests/test_trade_report_ai.py -k "trade_summary or horizon"`

Result:

- targeted report tests: 2 passed
- report summary/horizon subset: 18 passed, 116 deselected

## Follow-Up

- Confirm the next real `ai_trade_summary.md` has the added evidence lines under `## 진입 판단` and `### 청산 트리거`.
