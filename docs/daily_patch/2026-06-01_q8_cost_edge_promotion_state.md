# 2026-06-01 Q8 Cost Edge Promotion State

## EOD check

- Kiwoom account snapshot saved: `data/logs/kiwoom_account_snapshots/2026-06-01/latest.json`
- Trade reports checked: 7 reports, all closed and AI summaries available.
- Daily operator summary: 7 closed trades, 0 wins / 7 losses, average return -1.5186%.

## Q8 status

- Actual/live sample is still insufficient for full Q8 graduation: 7 valid trades vs target 20.
- Shadow surface is ready: 1155 evaluated candidates, 13 would-enter candidates.
- Dominant shadow blocker is cost-edge/cost-floor failure.

## Promotion decision

Cost-edge is already promoted in the live monitor path.

- `graphs/nodes/monitor_node.py` builds `quant_entry_decision`.
- `libs/runtime/quant/enforcement.py` enforces `cost_edge_fail` as a mandatory blocker.
- A triggered entry with `cost_edge_fail` becomes `quant_entry_block:cost_edge_fail` and no buy intent is emitted.

This patch updates Q8 reporting so the promotion candidate is shown as:

- action: `already_promoted_monitor_hard_gate`
- state: `active`
- effect: `entry_guard_enforced`

No additional live behavior change was added for cost-edge today. The change prevents Q8 reports from repeatedly recommending a guard that is already active.

## Verification

- `venv\Scripts\python.exe -m pytest tests\test_quant_shadow_candidate_evaluation.py tests\test_quant_decision.py -q`
- Result: 20 passed.
