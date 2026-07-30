# Quant Trade Diagnosis Report Plan

## Implementation Status

`IMPLEMENTED_2026_07_30`

The report is implemented as an independent reporting module:

```text
libs/reporting/quant_trade_diagnosis/
  builder.py
  markdown.py
  writer.py
```

Backfill and manual runner:

```text
python scripts/run_quant_trade_diagnosis.py --day YYYY-MM-DD
python scripts/run_quant_trade_diagnosis.py --start YYYY-MM-DD --end YYYY-MM-DD
```

The Q9 daily evaluation pipeline also generates the JSON and Markdown files
for every discovered trade. This integration is reporting-only and does not
call Scanner, Strategist, Commander, Monitor, order, or execution code.

Initial backfill:

- range: 2026-06-01 through 2026-07-29
- trade directories: 107
- JSON artifacts written: 107
- Markdown artifacts written: 107
- JSON parse errors: 0
- Markdown encoding replacement characters: 0
- finite broker/read-model outcomes: 101
- unresolved outcomes retained as unavailable: 6
- historical strategy-option score surfaces available: 0

Historical strategy-option scores were not retained in the authoritative
artifacts. The report therefore emits `INSUFFICIENT_EVIDENCE` and never
reconstructs or invents those scores.

## Purpose

`ai_trade_summary.md` is useful for trade facts and operator review, but it is not enough to quickly answer:

- Why did the system select this symbol?
- Which strategy frame allowed it?
- Did Scanner, Strategist, Commander, or Monitor add or remove value?
- Was the trade loss caused by selection, timing, exit, cost, or repeated same-symbol churn?

After Q13/Q14 validation, add a separate quant-style diagnosis report rather than replacing the existing trade summary.

Target artifact:

```text
reports/trades/YYYY-MM-DD/HHMM/TRD_.../reports/quant_trade_diagnosis.md
```

Optional JSON companion:

```text
reports/trades/YYYY-MM-DD/HHMM/TRD_.../reports/quant_trade_diagnosis.json
```

## Relationship To Existing Reports

| Report | Primary Purpose |
| --- | --- |
| `ai_trade_summary.md` | Operator-facing trade summary and LLM review |
| `q13_entry_timing_attribution_report.md` | Entry timing attribution across trades |
| `scanner_alignment_root_cause_report.md` | Q14 scanner alignment root-cause review |
| `quant_trade_diagnosis.md` | Single-trade, quant-style explanation of the full decision chain |

Do not replace `ai_trade_summary.md`. Add this as a separate diagnostic report after validation freeze completes.

## Report Structure

### 1. Executive Diagnosis

Short conclusion in plain language.

Example:

```text
The trade was not caused by Strategist override. Scanner repeatedly ranked 036420 as Top1 in a risk-off market, Commander preserved rank1-only scope, and Monitor entered only when breakout/VWAP/volume confirmation appeared. Loss came from low net edge, rapid trend breakdown, and repeated same-symbol churn.
```

### 2. Market Regime And Strategy Frame

Show the market condition that shaped the strategy.

Fields:

- market regime
- market regime rail
- KOSPI / KOSDAQ / KOSPI200 move
- KRX night futures move
- global sentiment score
- VIX level and change
- selected playbook
- tactical strategy
- risk tone
- trade aggressiveness

### 3. Strategy Candidate Scores

Show why one strategy frame won over alternatives.

Example:

| Strategy | Score | Result |
| --- | ---: | --- |
| defensive_observe | 0.55 | selected |
| vwap_reclaim_pullback | 0.5409 | rejected, below selected |
| reversal_reclaim | 0.5114 | rejected |
| opening_range_breakout | 0.4659 | rejected |

### 4. Selection Authority Chain

Show whether the selected symbol changed across agents.

Fields:

- raw scanner top1
- post-strategy top1
- selected symbol
- commander candidate
- executed symbol
- rank
- selection mismatch flag

### 5. Scanner Ranking Evidence

Explain why the symbol was ranked.

Fields:

- scanner rank
- score total
- pre-adjust score
- confidence
- risk score
- score decomposition if available
- repeated symbol penalty
- theme boost
- volume/momentum/trend contribution

Interpretation should be explicit:

- Was this a strong absolute candidate?
- Or only a weak-market relative Top1?
- Did risk score conflict with rank?

### 6. Commander Control

Show how Commander constrained the trade universe.

Fields:

- mode
- max priority rank
- max runner-ups
- cascade enabled
- runner-up policy
- reason

### 7. Monitor Entry Diagnosis

Explain why Monitor entered or blocked.

Fields:

- decision
- entry reason
- entry pattern
- entry quality score
- volume ratio
- VWAP state
- breakout state
- pullback state
- cost edge state
- hard blockers
- no-trade surface if blocked before entry

This section must clearly distinguish:

- high chart quality but hard gate failed
- strong entry score but insufficient volume
- same-symbol-position block
- breakout confirmed with weak net edge

### 8. Monitor Exit Diagnosis

Explain why Monitor exited.

Fields:

- exit reason
- active exit axis
- stop loss state
- trend breakdown state
- hold time
- min/target horizon compliance
- cost-aware floor state
- sell guard / broker availability issues

### 9. Trade Outcome Table

Use broker truth.

For repeated same-symbol days, include the whole symbol-level sequence and mark the current trade row.

### 10. Root Cause Attribution

Use Q13/Q14 evidence when available.

Candidate labels:

- Scanner Ranking Failure
- Candidate Filtering
- Strategist Override
- Commander Over-Filtering
- Entry Too Early
- Entry Too Late
- Exit Horizon Violation
- Cost Edge Failure
- Same-Symbol Churn
- Missing Evidence

### 11. Quant Interpretation

Write a short analysis in quant language.

Required points:

- Was the trade thesis statistically plausible?
- Did the signal have enough expected move after costs?
- Did the chosen horizon match the exit behavior?
- Did market regime justify rank1-only policy?
- Was the loss from signal selection, timing, exit, or cost drag?

### 12. Next Evaluation Questions

This is not a behavior patch section. It should only list evidence questions.

Examples:

- Did Scanner Top1 outperform Top3/Top5 alternatives?
- Did same-symbol repeated entries underperform after first loss?
- Did defensive_observe produce enough forward MFE to justify trading?
- Did exits occur before the strategy horizon had a fair chance?
- Did cost-edge fail despite chart-quality score being high?

## Data Sources

Primary sources:

- `lifecycle_bundle.json`
- `entry.json`
- `exit.json`
- `evidence/scanner_evidence.json`
- `evidence/strategist_evidence.json`
- `evidence/commander_evidence.json`
- `evidence/monitor_evidence.json`
- `reports/evaluation/trades/YYYY-MM-DD/TRD_.../trade_read_model.json`
- `reports/evaluation/trades/YYYY-MM-DD/TRD_.../trade_evaluation.json`
- `reports/evaluation/daily/YYYY-MM-DD/selection_authority_audit.json`
- `reports/evaluation/daily/YYYY-MM-DD/scanner_alignment_root_cause_report.json`
- `reports/evaluation/daily/YYYY-MM-DD/entry_timing_attribution_report.json`
- `reports/reconciliation/broker_trade_reconciliation_YYYY-MM-DD.json`

Broker truth must remain authoritative for realized PnL.

## Timing

Do not implement during Q13/Q14 validation freeze.

Recommended timing:

1. Complete Q13/Q14 validation window.
2. Select Q15 behavior patch candidate.
3. Add `quant_trade_diagnosis.md` as an observability/reporting artifact.
4. Use it to compare before/after Q15 behavior patch.

## Governance

- This report is diagnostic only.
- It must not change scanner, strategist, commander, monitor, entry, exit, or execution behavior.
- It should support Q15 decision-making but not authorize multiple simultaneous behavior changes.
- It should make existing evidence easier to read, not introduce a new evaluation axis during freeze.
