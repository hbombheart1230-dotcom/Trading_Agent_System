# M31-10 Operator Visibility Layer Upgrade

- Date: 2026-03-07
- Objective: keep raw machine logs intact, add human-readable operator reports on top.

## New Components

1. `scripts/run_operator_daily_summary.py`
- Input:
  - `data/logs/events.jsonl`
  - `reports/metrics/metrics_<day>.json` (auto-generated if missing)
  - `reports/milestones/m30_post_golive/m30_post_golive_policy_<day>.json`
  - `reports/milestones/m30_golive/m30_final_golive_signoff_<day>.json`
  - `reports/milestones/m31_slo_incident/m31_slo_incident_<day>.json`
- Output:
  - `reports/operator_summary/operator_summary_<day>.md`
  - `reports/operator_summary/operator_summary_<day>.json`
- Sections:
  - Executive Summary
  - System Health Status
  - Trading Activity Summary
  - Safety Guard Interventions
  - Top Issues
  - Recommended Operator Actions

2. `scripts/run_decision_story_report.py`
- Input: `events.jsonl` run lifecycle events
- Output:
  - `reports/decision_story/decision_story_<day>.md`
- Per-run story:
  - run_id
  - symbol
  - final_action
  - execution_status
  - decision_reason_summary
  - technical_evidence
  - sentiment_evidence
  - guard_intervention
  - operator_intervention
  - final_outcome

3. `scripts/run_run_card_report.py`
- Input: `events.jsonl`
- Output:
  - `reports/run_cards/run_cards_<day>.md`
- Card fields:
  - run_id
  - symbol
  - action
  - qty
  - execution_status
  - guard_status
  - key_reason
  - risk_flags

## Health Classification

- `RED`
  - duplicate execution detected
  - guard precedence violation detected
  - M31 SLO/incident gate failed
  - escalation level is `incident`
- `YELLOW`
  - high API error (`api_429_rate > 20%`)
  - excessive blocked orders (`blocked_rate > 60%` with meaningful volume)
  - escalation level is `watch`
- `GREEN`
  - no critical/warning issues

## Integration Point

- File: `graphs/pipelines/m13_eod_report.py`
- Behavior:
  - standard EOD report is generated first
  - operator visibility bundle is auto-generated afterward
  - failures in operator report generation do not break EOD flow
  - generated paths are attached to `state["daily_report"]["operator_visibility"]`

## Example Commands

```bash
python scripts/run_operator_daily_summary.py --day 2026-03-07 --json
python scripts/run_decision_story_report.py --day 2026-03-07 --json
python scripts/run_run_card_report.py --day 2026-03-07 --json
```

## Example Operator Summary (MD)

```md
# Operator Daily Summary (2026-03-07)

## Executive Summary
- system_status: **YELLOW**
- Runs=128, actions={'BUY': 12, 'SELL': 8, 'NOOP': 108}, executions=14 (ok=14, fail=0).
- Guard blocks=23, top_block_reason=MAX_NOTIONAL exceeded (11), interventions=2.
- LLM success_rate=97.30%, health=YELLOW.

## System Health Status
- system_health_level: **YELLOW**
- reasoning:
  - blocked_rate=64.00% (32/50)
- recommended_action:
  - Review allowlist, notional limits, and decision thresholds causing frequent guard blocks.
```

