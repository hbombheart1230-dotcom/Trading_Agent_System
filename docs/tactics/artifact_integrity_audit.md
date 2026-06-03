# Artifact Integrity Audit

Purpose: define the read-only audit needed before strategy optimization resumes.

The goal is that one trade can be reconstructed from artifacts alone. This
document is an audit checklist and report template. It does not change runtime
behavior.

## Audit Scope

Validate these truth surfaces:

- broker truth
- lifecycle truth
- report truth
- quant tactic truth
- shadow evaluation truth
- post-exit observation truth

## Integrity Matrix

| Area | Required Fields | Pass Criteria | Status |
| --- | --- | --- | --- |
| Identity | `trade_id`, `day`, `symbol`, `symbol_name`, `trade_dir` | same trade identity across lifecycle, report, operator summary |  |
| Broker truth | order ids, fill ids, quantity, fill price, realized PnL, status | broker snapshot agrees with lifecycle/report for closed trades |  |
| Lifecycle truth | entry time, exit time, status, entry price, exit price, quantity | lifecycle reconstructs full trade path |  |
| Report truth | trade overview, status, PnL, symbol, theme, tactic fields | report matches lifecycle and broker truth |  |
| Trade count | broker trades, lifecycle bundles, reports | count differences are explained |  |
| PnL | realized value, percent, fees/tax basis, source | PnL source is explicit and consistent |  |
| Tactic fields | tactic id, suitability, cost floor state, pullback quality, blockers | no missing required evaluation fields |  |
| Candidate fields | top candidate, selected candidate, runner-up review, selection reason | selection path is reconstructable |  |
| Shadow fields | candidate snapshot, forward outcome, inferior/superior evidence | shadow result is populated or has explicit missing reason |  |
| Exit fields | exit quant decision, monitor exit reason, post-exit checkpoints | exit quality is reconstructable |  |

## Status Classes

- `PASS`: complete and internally consistent.
- `WATCH`: usable but missing non-critical evidence.
- `FAIL`: inconsistent or missing fields that weaken evaluation.
- `BLOCKER`: trade cannot be reconstructed or broker truth is contradicted.

## Missing Field Report

Use this format for missing fields:

| Trade | Field | Expected Source | Impact | Suggested Owner |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Inconsistent Field Report

Use this format for conflicts:

| Trade | Field | Source A | Source B | Preferred Truth | Impact |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## Duplicated Field Report

Use this format when the same concept is stored under multiple names:

| Concept | Field Names | Current Readers | Risk | Consolidation Target |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Unused Field Report

Use this format when artifacts contain fields that are not consumed by summary,
evaluation, or feedback surfaces:

| Field | Producer | Consumer | Keep/Remove/Deprecate | Reason |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Audit Rule

If broker truth, lifecycle truth, and report truth disagree, broker truth wins
for realized status, fill price, fill quantity, and realized PnL. Lifecycle and
report artifacts should then be treated as stale or incomplete until corrected.

## 2026-06-02 Broker-Lifecycle Mismatch Rule

Observed defect:

- Broker truth showed a symbol fully sold through `ka10170` day trade diary.
- Lifecycle/report truth initially remained open.
- The trade was not suitable for tactic evaluation until the lifecycle/report
  bundle was regenerated and aligned with broker truth.

Required daily report fields:

| Field | Source | Meaning | Required Status |
| --- | --- | --- | --- |
| `account_snapshot.day_trade_diary_rows` | `ka10170.tdy_trde_diary` | normalized same-day trade rows | present when API is available |
| `account_snapshot.day_trade_closed_symbols` | normalized `ka10170` rows | symbols where buy quantity was fully sold | populated for closed day trades |
| `trade_report_integrity.broker_closed_report_open_count` | daily report integrity cross-check | broker says closed but report/lifecycle is not closed | must be 0 |
| `trade_report_integrity.broker_closed_report_open` | daily report integrity cross-check | compact examples of mismatched trades | empty |

Status rule:

- `broker_closed_report_open_count == 0`: usable if all other integrity checks
  pass.
- `broker_closed_report_open_count > 0`: `BLOCKER`. Repair lifecycle/report
  artifacts before using the affected trades for Q8, scorecards, promotion, or
  Strategist feedback.

Preferred repair sequence:

1. Run broker trade reconciliation for the day.
2. Regenerate the affected live execution bundle/trade report from broker
   truth.
3. Regenerate daily report and operator summary.
4. Confirm `broker_closed_report_open_count` returns to 0.
