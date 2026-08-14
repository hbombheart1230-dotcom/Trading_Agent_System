# M2 Source Audit - 2026-08-14

## Scope

This audit records which persisted sources M2 can safely expose. It is a
read-only finding and does not authorize a Trading Runtime or report-generator
change.

## Accepted Sources

### Performance

Source:

```text
reports/performance/YYYY-MM-DD/summary.json
```

Accepted contract:

* schema is `performance_summary.v1`;
* artifact day matches its directory day;
* `trade_rows` is an object array;
* realized returns require `return_basis == truth_surface_net`;
* lifecycle-only and observed shadow returns are excluded;
* period aggregation deduplicates `trade_id`;
* `return` values are decimal ratios and API return output uses percent units;
* `pnl` is used only when numeric and attached to a trusted net row.

Actual 2026-06-01 through 2026-07-31 audit result:

| Item | Count |
| --- | ---: |
| Distinct trade rows | 110 |
| Trusted net return samples | 81 |
| Unresolved/non-truth rows | 29 |
| Invalid daily source files | 0 |

The period is therefore `PARTIAL`, not fully complete.

### Portfolio

Source:

```text
reports/operator_summary/daily/YYYY-MM-DD/daily_summary.json
```

Accepted surface:

```text
residual_positions
account_snapshot_reconciliation
closeout state already projected into the daily summary
```

The API labels this source `RECONCILED_CLOSEOUT_READ_MODEL`. It does not label
it as a direct live broker query.

## Rejected Direct Source

Audited path family:

```text
data/logs/kiwoom_account_snapshots/YYYY-MM-DD/*.json
```

Observed problems:

1. Some historical files contain mock request metadata instead of broker
   response truth.
2. Current response-bearing files can be invalid JSON because legacy Korean
   titles are mojibake and include an unescaped quote boundary.
3. Several API calls report transport `status=ok` while their payload contains
   `BAD_REQUEST` or a non-zero broker `return_code`.
4. The directory day and generation day can differ for report-regeneration
   snapshots, so filesystem modification time is not trading-day authority.

Decision:

* M2 request handlers do not parse this family directly.
* A malformed snapshot does not cause the API to invent an empty account.
* Current orders, gross PnL, explicit fees/taxes, and cost drag remain
  `UNAVAILABLE` until a valid canonical projection exists.
* Repairing snapshot serialization belongs to a separate Core/reporting defect
  task and is outside the Web/API isolation boundary.

## Availability Rules

| Situation | API status |
| --- | --- |
| Valid source and complete required values | `AVAILABLE` |
| Valid source with unresolved trade rows | `PARTIAL` |
| Valid source with no qualifying trades | `NO_DATA` |
| Missing daily artifact | `UNAVAILABLE` |
| Malformed or wrong-schema artifact | `ERROR` |
| Unsupported cost basis | `UNAVAILABLE` |

Zero is returned only when the source measured zero, such as a valid reconciled
flat portfolio. Missing source data is returned as null with a reason.
