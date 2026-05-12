# Horizon Slot Report Layout

## Status

HOLD / deferred design-only report layout note.

As of 2026-05-08, this is not the active implementation path. The active path
is `multi_position_minimal_patch_plan_2026-05-08.md`.

This document only preserves the earlier two-slot report idea for later review.
It does not change runtime behavior by itself.

Do not apply the slot report layout below unless the slot design is explicitly
reactivated. The current report path should remain non-slot-based.

## Decision

Reports should remain date-first.

The operator's daily review starts from one trading day, then compares two
holding-period slots inside that day:

- `short_term`
- `long_hold`

Do not make the slot the top-level report directory. A slot-first layout would
force the operator to inspect multiple trees for one trading day.

## Trade Report Layout

Target layout:

```text
reports/trades/
  2026-05-08/
    _daily_summary.md
    _slot_summary.json
    short_term/
      0900/
        TRD_...
      1000/
        TRD_...
    long_hold/
      open/
        TRD_...
      closed/
        TRD_...
```

Rejected layout:

```text
reports/trades/short_term/2026-05-08/...
reports/trades/long_hold/2026-05-08/...
```

Reason: the daily review and daily report generation are day-centered. The
operator should be able to open one date folder and inspect all slot outcomes.

## Operator Summary Layout

`reports/operator_summary` should not mirror every trade artifact path. It is
the operator-facing index and first review surface.

Target daily layout:

```text
reports/operator_summary/
  daily/
    2026-05-08/
      operator_summary.md
      operator_summary.json
      trade_index.json
      slot_summary.md
      slot_summary.json
      slots/
        short_term.md
        long_hold.md
```

`operator_summary.md` remains the first file to read. It should include a
compact slot comparison table before deep trade details:

```text
| slot | state | symbol | trades | win_rate | net_return | avg_hold | main_exit | note |
|---|---|---:|---:|---:|---:|---:|---|---|
| short_term | live | 073490 | 3 | 0% | -1.2% | 95s | peak_drawdown | fee/exit drag |
| long_hold | ready | - | 0 | - | - | - | - | not tested today |
```

`slots/*.md` files are drill-down views. They should include:

- slot state: live, ready, shadow, disabled
- current or last symbol
- trade count
- win rate
- gross return
- net return after fee/tax
- average hold time
- main entry pattern
- main exit pattern
- slot capacity rejections
- same-symbol cross-slot rejections
- unresolved data-quality issues

## Weekly and Monthly Layout

Weekly and monthly summaries should keep their current period-first structure
and add slot-level summaries:

```text
reports/operator_summary/
  weekly/
    2026-W19/
      weekly_summary.md
      weekly_summary.json
      slot_summary.md
      slot_summary.json
  monthly/
    2026-05/
      monthly_summary.md
      monthly_summary.json
      slot_summary.md
      slot_summary.json
```

The goal is to separate performance diagnosis:

- total system win rate
- `short_term` win rate and cost drag
- `long_hold` hold quality, overnight gap behavior, and multi-day exit quality

Without this split, weak short-term results can hide whether longer holding is
untested or actually underperforming.

## Symbol Summary Layout

`reports/operator_summary/symbols/{symbol}` should remain symbol-first.

Do not create separate symbol folders per slot. The same symbol is not allowed
to be active in both slots at the same time, so one symbol folder should own the
full history.

Add slot breakdown fields inside the existing symbol files instead:

```text
reports/operator_summary/
  symbols/
    005930/
      symbol_summary.md
      symbol_summary.json
      trade_history.json
      latest_snapshot.json
```

Required symbol-level slot fields:

- `slot_breakdown`
- `last_horizon_slot`
- `last_slot_trade_id`
- `same_symbol_cross_slot_rejections`
- slot-level win rate and net return where enough data exists

## Current Classification Note

Recent live trade reports are effectively `short_term`.

Evidence:

- The current live loop is chart-driven and intraday.
- Expected hold window is usually minutes, not days.
- Actual holds are often tens of seconds to several minutes.

Raw historical values such as `scalp`, `intraday`, `overnight_probe`, and
`1_2day_swing` should be mapped into the two-slot view for current reporting:

- `scalp` and `intraday` -> `short_term`
- `overnight_probe`, `1_2day_swing`, and multi-day hold -> `long_hold`

## Implementation Order

1. Persist `horizon_slot` into trade bundle and report artifacts.
2. Route new trade report folders to
   `reports/trades/{day}/{horizon_slot}/{time_bucket}/{trade_id}`.
3. Add daily `slot_summary.md/json` under `reports/operator_summary/daily/{day}`.
4. Add slot comparison section to daily `operator_summary.md`.
5. Add weekly/monthly slot summaries.
6. Add symbol-level `slot_breakdown` without splitting symbol folders.
7. Backfill older reports only after the new live path is stable.

## Backfill Rule

Do not aggressively move older report folders before the new slot metadata is
stable.

For old reports, prefer an index-level migration first:

- infer `horizon_slot` where possible
- write `slot_summary.json`
- leave original trade folders in place

Physical folder moves can follow later if report links and symbol histories are
confirmed clean.
