# Product Data Contract v1

## 1. Purpose

This contract fixes the meaning of the operating and portfolio metrics before
the API and UI aggregate them. It prevents different screens from calculating
the same label differently.

This is a read-only presentation contract. It does not change broker, trading,
evaluation, report, or runtime behavior.

## 2. Time Contract

* Canonical operating timezone: `Asia/Seoul`.
* Intraday grouping uses the Korean trading date.
* Realized performance is attributed to the broker-authoritative exit date.
* Trade history retains both entry date and exit date.
* Carryover positions are not counted as a new trade on the next day.
* An unresolved/open position is excluded from realized win-rate and average-
  return denominators.
* API timestamps are ISO 8601 with an explicit offset.

Supported product periods:

* today
* last 5 trading days
* last 20 trading days
* calendar month
* explicit date range
* all trusted history

## 3. Truth Priority

| Data | Authority order |
| --- | --- |
| Order, fill, position, realized PnL | Kiwoom broker truth |
| Trade identity and lifecycle | reconciled lifecycle bundle |
| Entry/exit decision lineage | canonical trade/read-model artifacts |
| Candidate, rank, block, forward outcome | Q9/evaluation artifacts |
| Strategy, tactic, horizon | canonical Strategist/Commander artifacts |
| Market context | timestamped macro-indicator artifact |
| Human explanation | AI summary/report, never numeric authority |

When authorities disagree, the API must return a `DataQualityIssue`. It must
not silently select a convenient value.

## 4. Cost Bases

Every return and PnL metric declares one cost basis:

* `GROSS`: price movement before fees, tax, and slippage.
* `MOCK_BROKER_NET`: broker-reported mock result using the observed mock cost
  profile.
* `LIVE_EQUIVALENT_NET`: research comparison using the fixed live-equity cost
  assumption and separately stated slippage.
* `NOT_APPLICABLE`: counts, market values, and non-return metrics.

Different cost bases must never be merged into one time series or average.
UI comparison may place them side by side with explicit labels.

## 5. Performance Definitions

### Trade Count

* `opened_trade_count`: distinct trusted entry lifecycles.
* `closed_trade_count`: distinct trusted closed lifecycles.
* `realized_exit_count`: broker-authoritative completed exits.
* `open_position_count`: current broker-authoritative positions.
* `flat_count`: resolved returns equal to zero within the source precision.

Partial fills belonging to one lifecycle are not separate trades.

### Win Rate

```text
directional_resolved_count = win_count + loss_count
win_rate = win_count / directional_resolved_count
```

Flat and unresolved trades are shown separately and excluded from the canonical
win-rate denominator. The API always returns the denominator counts.

### Average Return

Arithmetic mean of trusted resolved return samples under one cost basis. Missing
or unresolved return values are excluded and reported as missing counts.

### Average Gain and Average Loss

* average gain: mean of returns greater than zero;
* average loss: mean of returns less than zero;
* no qualifying sample produces `NO_DATA`, not `0`.

### Profit Factor

```text
profit_factor = sum(positive returns) / abs(sum(negative returns))
```

If there are no negative samples, Profit Factor is unavailable/infinite by
definition and must not be serialized as an arbitrary large number. The API
returns `NO_DATA` with a reason.

### Maximum Drawdown

Maximum peak-to-trough decline from the chronologically ordered cumulative
return or equity series. The response identifies which input was used.

### Cost Drag

```text
cost_drag = gross_result - corresponding_net_result
```

Cost drag is computed only for paired observations of the same trade/outcome.

### MFE and MAE

MFE/MAE use the same reference entry, symbol, horizon, and price source. They
are never mixed across horizons.

## 6. Availability Semantics

Canonical states:

* `AVAILABLE`: source and required fields are complete.
* `PARTIAL`: usable result with explicit missing coverage.
* `UNAVAILABLE`: source or required contract is absent.
* `STALE`: source exists but is older than its freshness contract.
* `NO_DATA`: source is healthy but no qualifying observation exists.
* `ERROR`: source exists but cannot be parsed or validated.

`0` is a valid measured value. It is never used as a substitute for missing,
unavailable, unresolved, or insufficient data.

## 7. Required Metric Metadata

Every metric or series includes:

* status
* value and unit
* cost basis
* period
* sample count
* missing sample count where applicable
* coverage where applicable
* generated time
* as-of time
* source/provenance

Research and shadow metrics also declare `behavior_effect` and must not be
presented as realized performance.

## 8. Generic Product Models

The public API is based on domain models rather than broker or Q-phase schemas:

* `Trade`
* `Portfolio`
* `PerformanceSummary`
* `PerformanceSeries`
* `Opportunity`
* `StrategyBreakdown`
* `MarketSnapshot`
* `DataQualityIssue`

Source-specific fields remain in provenance or adapter diagnostics. They do
not become required UI fields.

## 9. Public Portfolio Boundary

The public profile removes:

* account number
* order and fill identifiers
* absolute filesystem paths
* raw prompts and LLM responses
* API keys and environment values
* process IDs and host-specific information

It retains truthful mode identification, including simulation/mock status, and
uses the same metric formulas as the internal operating profile.
