# 2026-05-12 Candidate Cascade Expansion Hotfix

## Reason

After the 2026-05-11 candidate expansion patch, live cycles still produced no BUYs even with capacity available. The current blocker was `below_vwap_reclaim_not_ready`, but the deeper issue was policy inconsistency:

- Commander expanded entry scope to `max_priority_rank=10` and `max_runner_ups=9`.
- The same entry control still carried the strategist proposal's stale `cascade_enabled=false`.
- Monitor honored that false flag and reported `cascade_disabled_by_entry_control`, so it kept checking only the top scanner candidate.

## Patch

- Commander now explicitly sets `cascade_enabled=true` when `expand_when_market_ok` expands the candidate pool after repeated expandable blockers.
- Monitor now treats `candidate_watch_policy_effect=commander_expanded_repeated_blocker` or `mode=expand_when_market_ok` as an executable cascade expansion, even if a stale strategist proposal left `cascade_enabled=false`.
- VWAP reclaim and other hard entry gates remain unchanged. The patch only restores runner-up evaluation when Commander already decided that the candidate pool should expand.

## Validation

- `python -m py_compile graphs\commander_runtime.py graphs\nodes\monitor_node.py` passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_m21_commander_runtime_entry.py::test_commander_keeps_candidate_expansion_when_status_blocked_but_capacity_available tests\test_monitor_exit_guard.py::test_monitor_entry_candidate_cascade_uses_commander_priority_expansion tests\test_monitor_exit_guard.py::test_monitor_falls_back_to_runner_up_when_top_pick_reclaim_waits` passed: 3 passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_monitor_candidate_cascade.py tests\test_monitor_feedback_adaptive_policy.py` passed: 12 passed.
- `.\venv\Scripts\python.exe -m pytest -q tests\test_monitor_exit_guard.py::test_monitor_does_not_fallback_when_open_position_exists tests\test_monitor_exit_guard.py::test_monitor_cascades_from_held_top_pick_when_capacity_remains` passed: 2 passed.

## Live Check

Next live cycles should show monitor `entry_candidate_cascade` with:

- `max_priority_rank=10`
- `max_runner_ups=9`
- `cascade_enabled=true`
- no `cascade_disabled_by_entry_control` when repeated expandable blockers and capacity remain.
