# Broker Stale Fill Reconciliation Fix - 2026-07-22

## Classification

- Scope: artifact integrity and broker-truth reconciliation
- Behavior change: none
- Entry, exit, ranking, Strategist, Commander, and Monitor logic: unchanged
- Freeze compatibility: permitted observability/integrity defect fix

## Defect

On 2026-07-17 the mock broker returned the previous session's `ka10076`
fills even though the request-day order-history APIs contained no fills.

The closed-trade reconciler treated those undated rows as proof of a current-day
round trip and synthesized four false `001790` trades. The false artifacts then
contaminated trade evaluation and symbol history.

## Authority Rule

`ka10076` has no trading-day parameter. Its rows may enrich fee information,
but they must never establish that a trade occurred on a requested day.

Synthetic trade creation and order-pair matching now require:

1. a snapshot whose `day` matches the requested day;
2. `kt00009` rows returned from an `ord_dt` request matching that day;
3. a complete same-symbol buy/sell pair in those date-scoped rows.

Each synthesized broker bundle records:

- `source_api=kt00009`
- `query_day=YYYYMMDD`

This provenance remains available to downstream integrity audits.

## Repair

- The four false 2026-07-17 source and evaluation bundles were moved to
  `data/logs/artifact_quarantine/2026-07-17_stale_ka10076/`.
- The 2026-07-17 Q9 evaluation was regenerated with `trade_count=0`.
- The `001790` symbol report was regenerated from active source artifacts.
- A full scan of remaining broker-synthesized bundles found no other active
  bundle missing its date-scoped broker order IDs.

## Verification

- Targeted and related regression tests: 163 passed.
- Real 2026-07-17 snapshot replay:
  - authoritative dated orders: 0
  - undated fee/fill rows: 8
  - synthesized trades: 0

