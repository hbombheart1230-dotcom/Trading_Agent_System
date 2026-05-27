# 2026-05-26 Opening Momentum Probe Shadow

## Purpose

Strong risk-on openings can run before the existing pullback/VWAP maturity
rules become ready. This patch adds an observation-only opening momentum probe
lane so Q8 can measure those missed early opportunities without changing live
orders.

## Changed

- `libs/runtime/quant/shadow_candidates.py`
  - Adds `opening_momentum_probe_shadow` to each evaluated shadow candidate.
  - Counts `opening_momentum_probe_would_enter_count` in the shadow payload
    summary.
- `libs/reporting/quant_shadow_candidate_evaluation.py`
  - Aggregates opening probe candidate count, would-probe count, reasons, and
    would-probe symbols.
  - Renders `Opening momentum probe shadow` lines in operator summaries.

## Probe Criteria

Observation-only `would_probe` requires:

- first 20 minutes after 09:00 KST
- cost edge/floor is met
- volume ratio >= 0.8
- price is at or above VWAP
- breakout, weighted monitor score, or human chart entry score confirms momentum

## Behavior

- No real buy/sell behavior changes.
- No scanner ranking changes.
- No entry guard bypass.
- Q8 comparison remains separated from existing `would_enter`.

## Verification

- `venv\Scripts\python.exe -m pytest tests/test_quant_shadow_candidates.py tests/test_quant_shadow_candidate_evaluation.py tests/test_operator_summary_reports.py -q`
  - 30 passed
- `venv\Scripts\python.exe -m py_compile libs/runtime/quant/shadow_candidates.py libs/reporting/quant_shadow_candidate_evaluation.py`

## 2026-05-27 Largecap Surge Shadow Follow-up

The 2026-05-27 open showed that `005930` nearly passed the existing opening
momentum probe (`volume_ratio 0.759` vs fixed `0.8` floor), while `000660` and
`009150` were not surfaced in the 09:00-09:20 shadow set early enough.

Changed:

- Added `libs/runtime/quant/opening_largecap_surge_shadow.py`.
- Added observation-only `opening_largecap_surge_shadow` to shadow rows.
- Added opening watchlist shadow rows from `ranked_candidates` for:
  - `005930`
  - `000660`
  - `009150`
- Added operator summary counts:
  - `opening_largecap_surge_count`
  - `opening_largecap_surge_would_enter_count`
  - `Opening largecap surge shadow`

Observation-only criteria:

- first 20 minutes after 09:00 KST
- symbol is in the largecap surge watchlist
- cost edge/floor is met
- volume ratio >= `0.72`
- price is at or above VWAP
- breakout, weighted score, or human chart score confirms momentum

Behavior:

- No real buy/sell behavior changes.
- No scanner ranking changes.
- No entry guard bypass.
- The patch only records whether a largecap opening surge lane would have
  flagged a missed early move.

Verification:

- `venv\Scripts\python.exe -m pytest tests/test_quant_shadow_candidates.py tests/test_quant_shadow_candidate_evaluation.py -q`
  - 14 passed
