# M5 Web UI Implementation - 2026-08-14

## Result

M5 adds an independent React, TypeScript, and Vite operating console under
`apps/web`. It consumes only the frozen M0-M4 GET API contracts.

Local services:

```text
Web: http://127.0.0.1:5173
API: http://127.0.0.1:8000
```

The Web development server proxies `/api` and `/health` to the API. The browser
does not access reports, logs, Trading Core, or Kiwoom directly.

## Product Navigation

The UI uses operating domains rather than evaluation phase names:

1. Overview
2. Performance
3. Trades
4. Opportunities
5. Strategies
6. Market
7. Reports
8. Data Quality

Q-phase artifacts remain provenance. There is no validation-progress page.

## Implemented Views

### Overview

* read-only, simulation, API, and execution-callable state;
* daily realized PnL, win rate, average return, profit factor, and positions;
* 75-day cumulative PnL and daily average-return chart;
* portfolio authority and data issues.

### Performance

* date-range selection;
* mock-broker net counts and metrics;
* cumulative PnL and average-return series;
* explicit gross and cost unavailability.

### Trades and Reports

* date, symbol, and result filtering;
* entry, hold, strategy, rank, PnL, and artifact status;
* decision lineage, timeline, broker reconciliation, and post-exit path;
* fixed report allowlist only;
* Markdown displayed as plain text, never executed as HTML;
* sanitized JSON display.

### Opportunities

* shadow-only label fixed at the page header;
* raw, deduplicated, and duplicate candidate counts;
* current signal state and features;
* blocker distribution;
* gross, live-equivalent, and mock-net forward outcomes kept separate;
* +5m, +15m, +30m, +60m, and EOD selection.

### Strategies

* playbook, tactic, horizon, and theme dimensions;
* count, coverage, win rate, average return, profit factor, and drawdown;
* missing strategy fields remain visible through partial status.

### Market

* KOSPI, KOSDAQ, KRX night futures, NASDAQ, and breadth summary;
* selectable indicator series;
* all collected rates, FX, equity, and derivatives metrics;
* source and role visible without fetching new data.

### Data Quality

* source-root readiness;
* read-only and execution-callable boundary;
* trade and forward coverage;
* combined artifact issues without mutation controls.

## Frontend Boundaries

```text
apps/web/src/
  app/                 navigation and route composition
  shared/              API client, formatters, states, layout
  features/overview/
  features/performance/
  features/trades/
  features/opportunities/
  features/strategies/
  features/market/
  features/reports/
  features/data-quality/
```

Feature source files are currently 108 lines or fewer. Pages are lazy-loaded;
the initial common JavaScript chunk is approximately 203 KB before gzip.

## Safety

The UI contains no:

* order, cancel, approve, or reject command;
* execution or environment toggle;
* API key input;
* POST, PUT, PATCH, or DELETE request;
* raw HTML Markdown execution;
* direct filesystem or provider access.

The API and Web bind to `127.0.0.1`. No Trading Runtime process was restarted.

## Verification

```text
Web unit tests: 3 passed
Web TypeScript/production build: passed
API + existing Operator UI regression: 94 passed, 1 skipped
Browser smoke: 8 routes x desktop/mobile = 16 renders passed
Console/page errors: 0
Document horizontal overflow: 0
API readiness through Web proxy: AVAILABLE
Execution callable: false
```

Browser smoke uses the installed Chromium-compatible browser and stores
temporary screenshots outside the repository.

## Tooling Note

The host did not have Node.js. A portable official Node.js LTS v24.19.0 was
placed under the user Codex tools directory; it did not modify Trading Runtime
or the repository Python environment. Docker is not installed, so M7 container
work remains a later milestone.
