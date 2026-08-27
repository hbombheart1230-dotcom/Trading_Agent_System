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

## AI Evidence Provenance

From 2026-08-26 onward, new Q9 decision windows can carry stable evidence IDs
for Reporter feedback and memory packets. This allows later reports to answer:

- which feedback packet was exposed and consumed
- whether a Strategist frame change was observed in that decision
- which memory packets were visible and deterministically applied
- whether the Scanner universe was eligible as a strategy-neutral control

The records deliberately keep `causal_attribution=false`. Performance impact
requires a linked forward outcome and a valid control; packet visibility alone
does not establish value.

Implemented scorecard outputs:

- `reports/evaluation/agent_effectiveness/YYYY-MM-DD/agent_effectiveness_scorecard.json`
- `reports/evaluation/agent_effectiveness/YYYY-MM-DD/agent_effectiveness_scorecard.md`

The baseline generated from the trusted 2026-06-01 through 2026-07-29
full-chain review is stored under `2026-07-29`. Daily Q9 runs append a daily
increment; they do not rescan the complete historical minute-price state.
