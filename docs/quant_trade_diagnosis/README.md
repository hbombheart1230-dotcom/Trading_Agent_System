# Quant Trade Diagnosis

Active documents:

- `agent_effectiveness_scorecard_framework.md`: current authority for deciding
  whether Scanner, Strategist, Commander, Monitor Entry, and Monitor Exit add
  value, degrade their input baseline, or remain unmeasurable
- `quant_trade_diagnosis_report_plan.md`: implemented per-trade report contract
- `integrated_selection_horizon_sequence_evaluation_2026-07-31.md`: current
  integration decision for selection, horizon, exit, reactivation, and
  same-symbol sequence evidence

`quant_trade_diagnosis` is a reporting adapter. It does not independently
authorize behavior changes. Promotion decisions must use the integrated range
evaluation and broker-authoritative outcomes.

The per-trade diagnosis explains what happened. The Agent Effectiveness
Scorecard Framework decides how those explanations become cumulative component
judgments. Neither artifact directly changes runtime behavior.

Implemented scorecard outputs:

- `reports/evaluation/agent_effectiveness/YYYY-MM-DD/agent_effectiveness_scorecard.json`
- `reports/evaluation/agent_effectiveness/YYYY-MM-DD/agent_effectiveness_scorecard.md`

The baseline generated from the trusted 2026-06-01 through 2026-07-29
full-chain review is stored under `2026-07-29`. Daily Q9 runs append a daily
increment; they do not rescan the complete historical minute-price state.
