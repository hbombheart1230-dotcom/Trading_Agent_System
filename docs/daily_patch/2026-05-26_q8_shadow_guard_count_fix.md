# 2026-05-26 Q8 Shadow Guard Count Fix

## Problem

`Quant Shadow Candidates` could over-count `entry_guard` because rows with
`primary_failure_axis=confirmed_entry` and `entry_quant_decision=entry_ready`
were counted as guard-blocked promotion evidence.

That made `Q8 promotion candidate: entry_guard` look stronger than it was.

## Changed

- `libs/runtime/quant/shadow_candidates.py`
  - Stores `guard_reason`, `intent_submitted`, and `buy_blocked_*` fields.
  - Derives `entry_quant_cost_floor_state` from entry quant decision or factor
    snapshot when selected candidate metadata does not have it.
- `graphs/nodes/monitor_node.py`
  - Adds runner-up guard and buy-block detail fields to fallback trace.
- `libs/reporting/quant_shadow_candidate_evaluation.py`
  - Excludes `confirmed_entry + entry_ready + no blockers + no guard_reason`
    rows from actionable entry-guard promotion counts.
  - Counts `entry_quant_decision.blockers` and nested `cost_edge.cost_floor_state`
    for cost-edge promotion evidence.
  - Adds `actionable_guard_blocked_count` to summary output.

## Behavior

- Live entry behavior is unchanged.
- Q8 promotion recommendation is corrected.
- A restart is required for new runtime shadow rows to include the additional
  fields.

## Verification

- `venv\Scripts\python.exe -m pytest tests/test_quant_shadow_candidate_evaluation.py tests/test_quant_shadow_candidates.py tests/test_operator_summary_reports.py -q`
  - 28 passed
- `venv\Scripts\python.exe -m py_compile libs/runtime/quant/shadow_candidates.py libs/reporting/quant_shadow_candidate_evaluation.py graphs/nodes/monitor_node.py`
