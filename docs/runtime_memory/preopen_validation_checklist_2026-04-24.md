# Preopen Validation Checklist 2026-04-24

## Scope

Use this checklist on the next preopen / early intraday cycle after the latest runtime-memory and commander-control changes.

Focus:

- same-day reporter direct source
- commander memory policy signals
- monitor hold/exit bias application
- symbol-memory strength/recency damping

## 1. Reporter Feedback Direct Source

Verify on the first strategist artifact that same-day feedback does not wait for prebuilt metrics files.

Expected checks:

- `reports/canonical/<day>/<run_id>/strategist.json`
- `memory_packet_visibility.reporter_feedback_packet.available = true`
- `memory_packet_visibility.reporter_feedback_packet.source_available = true`
- `memory_packet_visibility.reporter_feedback_packet.feedback_gate_reason = auto_accepted`

Prefer seeing at least one of:

- `source_reports.metrics = true`
- `source_reports.reporter_analysis = true`

If both are false, verify whether closed same-day trade-report fallback is the reason.

## 2. Commander Memory Policy Signals

Verify:

- `commander_memory_policy.policy_signals.primary_layer`
- `commander_memory_policy.policy_signals.preferred_risk_posture`
- `commander_memory_policy.policy_signals.system_health`
- `commander_memory_policy.policy_signals.monitor_only_ratio`
- `commander_memory_policy.policy_signals.report_focus_targets`

Check that these values are plausible for the actual session posture.

## 3. Monitor Memory Bias Entry / Hold / Exit

Verify on fresh `monitor.json`:

- top-level `monitor_memory_bias_applied`
- top-level `monitor_memory_bias_hold_applied`
- top-level `monitor_memory_bias_exit_applied`

Also verify:

- `threshold_snapshot.monitor_memory_bias_applied`
- `policy_ref.monitor_memory_bias_applied`
- `monitor_memory_bias_hold_deltas`
- `monitor_memory_bias_exit_deltas`

Expected trace surface:

- `exit_policy_guard_adjustments` contains:
  - `commander_memory_bias_hold:*`
  - `commander_memory_bias_exit:*`

## 4. Symbol-Memory Damping

On a symbol with existing symbol memory, verify reasons include:

- `symbol_evidence_strength:*`
- `symbol_recency_days:*`

If the symbol memory is stale or weak, verify that:

- symbol-side bias is damped or blocked
- commander rationale includes the matching gate reason

## 5. Trade Report Spot Check

For the first closed trade of the day, verify:

- `reports/trades/<day>/<trade_id>/reports/ai_trade_report.json`
- `reporter_evaluation.status = ok`
- `memory_application_surface.scanner_captured = true`
- `memory_application_surface.monitor_captured = true`

If live AI generation fails:

- verify `ai_trade_report_generation_finished` still exists
- verify deterministic fallback outputs are present
- verify no new partial trade artifact is left without `_health.json`

## 6. Entry/Exit Behavior Sanity

Behavioral sanity checks:

- no obvious over-tightening that kills all entries immediately
- no obvious premature exits caused solely by first-pass hold/exit deltas
- runner-up cascade still functions when top pick is blocked

If hold/exit deltas look too strong, collect:

- `monitor_memory_bias_reasons`
- `monitor_memory_bias_hold_deltas`
- `monitor_memory_bias_exit_deltas`
- matching `commander_memory_policy.policy_signals`

Use those artifacts before tuning any thresholds.
