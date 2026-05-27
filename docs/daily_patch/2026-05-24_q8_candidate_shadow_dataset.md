# 2026-05-24 Q8 Candidate Shadow Dataset

## Purpose

Q8 needs more evaluation data than completed trades alone can provide. This
patch records candidates that the monitor already evaluated or skipped without
changing live trading behavior.

## Changed

- Added `libs/runtime/quant/shadow_candidates.py`.
- Added `libs/reporting/quant_shadow_candidate_evaluation.py`.
- Hooked `graphs/nodes/monitor_node.py` to save candidate shadow JSON after the
  monitor cycle builds `entry_candidate_cascade`.
- Hooked operator daily/weekly/monthly/symbol summaries to surface Q8 shadow
  candidate aggregates.
- Added `tests/test_quant_shadow_candidates.py`.
- Added `tests/test_quant_shadow_candidate_evaluation.py`.

## Stored Data

Path:

- `data/logs/quant_shadow_candidates/YYYY-MM-DD/`
- `latest.json` is updated for quick inspection.

Captured roles:

- `top_pick`
- `runner_up_evaluated`
- `runner_up_skipped`

Captured fields include symbol, name, rank, scanner score, theme, tactic ID,
tactic suitability fields, trigger/block reason, guard status, cost edge, and
quant decision snippets when available.

## Reporting Surface

Operator summaries now include:

- `quant_shadow_candidate_evaluation`
- markdown section `Quant Shadow Candidates`

The section shows candidate count, payload count, evaluated count,
would-enter count, guard-blocked count, and top buckets for role, reason,
tactic ID, suitability, cost floor, and failure axis.

It also shows `Q8 promotion candidate` and `Q8 promotion counts` for:

- cost-edge
- runner-up
- entry-guard

This is `recommendation_only`; it does not change live behavior.

## Behavior

- `behavior_effect`: `observation_only`
- `promotion_candidate.behavior_effect`: `recommendation_only`
- No scanner ranking change.
- No monitor entry/exit decision change.
- Save errors are recorded in runtime state and do not block the live loop.

## Verification

- `venv\Scripts\python.exe -m pytest tests/test_quant_shadow_candidate_evaluation.py tests/test_quant_shadow_candidates.py tests/test_operator_summary_reports.py -q`
  - 24 passed
- `venv\Scripts\python.exe -m py_compile libs/runtime/quant/shadow_candidates.py graphs/nodes/monitor_node.py libs/reporting/quant_shadow_candidate_evaluation.py libs/reporting/operator_period_summary.py`
