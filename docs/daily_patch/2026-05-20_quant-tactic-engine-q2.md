# 2026-05-20 Quant Tactic Engine Q2

## Scope

Phase Q2 of `docs/tactics/quant_tactic_engine_phase_plan.md`.

This patch adds deterministic factor snapshots and wires them into scanner and
monitor payloads as observation-only data. It does not change ranking, entry,
exit, or order behavior.

## Changes

- Added `libs/runtime/quant/factors.py`
  - `build_factor_snapshot()`
  - `build_factor_snapshot_from_candidate()`
  - `build_factor_snapshot_from_monitor_entry()`
- Updated scanner payload helpers:
  - `libs/runtime/scanner/output_payloads.py`
  - `libs/runtime/scanner/output_snapshots.py`
- Updated monitor node:
  - attaches `quant_factor_snapshot` to `entry_info`
  - exposes the same snapshot in `monitor_output`
- Added `tests/test_quant_factors.py`

## Factor Surface

Candidate snapshots currently include:

- score/confidence/risk
- VWAP distance
- volume ratio / volume spike
- breakout gap
- scanner chart fit
- trend/cross-section/sector-relative strength
- news/theme component placeholders
- expected monitor block reason

Monitor entry snapshots currently include:

- VWAP distance
- volume ratio
- pullback depth
- breakout gap
- reclaim/volume/pullback/breakout checks
- confidence and entry quality
- cost floor state
- cost-adjusted edge
- human chart scores
- lower VWAP rebound probe flag

## Behavior

No live behavior change intended.

All snapshots carry:

- `behavior_effect=observation_only`

## Verification

Passed:

```powershell
venv\Scripts\python.exe -m pytest -q tests/test_quant_factors.py tests/test_quant_tactics.py tests/test_scanner_strategy_frame_integration.py
venv\Scripts\python.exe -m pytest -q tests/test_m21_commander_runtime_entry.py
venv\Scripts\python.exe -m pytest -q tests/test_monitor_candidate_cascade.py
```

Result:

- 21 passed
- 83 passed
- 9 passed

Known unrelated regression observed while running a broader mixed suite:

```powershell
venv\Scripts\python.exe -m pytest -q tests/test_quant_factors.py tests/test_quant_tactics.py tests/test_scanner_strategy_frame_integration.py tests/test_monitor_feedback_adaptive_policy.py
```

Result:

- 29 passed
- 1 failed:
  `tests/test_monitor_feedback_adaptive_policy.py::test_monitor_feedback_long_streak_diversification`

The failure is in commander diversification policy expectation
(`diversification_bias` expected `0.0`, actual `0.02`) and is outside the Q2
factor snapshot path.
