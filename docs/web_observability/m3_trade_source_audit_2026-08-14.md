# M3 Trade Source Audit - 2026-08-14

## Purpose

This document fixes how the read-only API reconstructs trade history and
reports without depending on Trading Runtime modules or the multi-GB event
ledger.

## Source Priority

### Full Trade Bundle

Primary normalized source:

```text
reports/trades/YYYY-MM-DD/HHMM/TRD_*/reports/ai_trade_summary_input.json
```

Additive detail sources:

```text
entry.json
hold.json
exit.json
_health.json
_provenance.json
evaluation_exclusion.json
reports/quant_trade_diagnosis.json
```

Responsibilities:

| Source | API responsibility |
| --- | --- |
| AI summary input | identity, theme, truth surface, strategy, tactic, horizon, post-exit |
| Entry/exit | broker-aligned timestamps, prices, quantities, execution reasons |
| Hold | bounded in-lifecycle observations only |
| Health/provenance | completeness, reconciliation, agent source type |
| Evaluation exclusion | whether the trade is eligible for evaluation |
| Quant diagnosis | Scanner score and normalized diagnostic context |

Absolute source paths in provenance are not returned.

### Performance Fallback

Fallback source:

```text
reports/performance/YYYY-MM-DD/summary.json
```

When a performance-ledger trade has no usable trade bundle, it remains visible
with:

```text
artifact_scope = PERFORMANCE_FALLBACK
artifact_status = PARTIAL
timeline = []
evaluation_eligible = false
issue = TRADE_BUNDLE_MISSING
```

The fallback may provide trusted net return and PnL. It does not invent symbol
name, theme, entry time, exit time, quantity, horizon, or agent decisions.

## Timeline Integrity

Only hold events between authoritative entry and exit timestamps are included.
Observed hold rows outside that lifecycle are excluded and reported as:

```text
HOLD_EVENT_OUTSIDE_LIFECYCLE
```

This prevents stale/pre-entry monitor rows from appearing as actual holding
decisions.

## Report Allowlist

Allowed human reports:

```text
ai-summary
quant-diagnosis
post-exit
strategist-summary
trade-report
```

Allowed normalized JSON reports:

```text
post-exit-data
quant-diagnosis-data
```

Raw prompts, raw LLM responses, arbitrary filenames, lifecycle bundles, and
unbounded JSON are not available through the API.

## Historical Coverage

Audit range: 2026-06-01 through 2026-07-31.

| Measurement | Count |
| --- | ---: |
| Performance-ledger trade identities | 110 |
| Usable full trade bundles | 86 |
| Performance fallback rows | 24 |
| Fully available display rows | 8 |
| Partial display rows | 102 |
| Rows missing symbol name | 77 |
| Rows missing theme | 94 |
| Unreadable trade directories encountered | 20 |
| Duplicate trade ID across day directories | 1 |

The single duplicate is a trade rooted under its original day and repeated
under a later day directory. M3 keeps one identity and reports the duplicate;
it does not count it as another trade.

## Interpretation

M3 makes the history visible and internally consistent, but it also proves that
historical display metadata is incomplete. The UI must show code-only or
partial states for affected rows. It must not present 110 rows as fully
reconstructable trades.

This finding is an observability/data-quality result. It does not justify a
trading, evaluation, Scanner, Monitor, Strategist, or Commander change.
