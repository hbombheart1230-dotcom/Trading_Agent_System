# M5.1 LLM Operations Implementation - 2026-08-14

## Purpose

M5.1 adds an operations-facing OpenRouter surface before M6. It answers:

* which model is configured for each LLM role;
* which model was actually observed for the selected day;
* how many stage calls succeeded or failed;
* what recent transport latency looks like;
* whether token and cost evidence is actually available.

It does not expose prompts, response text, credentials, or internal paths.

## API

```text
GET /api/v1/llm/operations?day=YYYY-MM-DD
```

The endpoint is read-only and imports no Trading Core modules.

### Evidence sources

1. `reports/llm/YYYY-MM-DD/*/*/strategist_stage*/response.json`
   - full-day stage, model, status, attempts, and saved timestamp;
   - generic duplicate strategist copies are excluded.
2. Trade-bundle LLM response artifacts
   - trade report, trade summary, and operator brief observations.
3. Bounded `data/logs/events.jsonl` tail
   - recent transport latency only;
   - maximum bytes and rows are controlled by `ApiSettings`.

The API never request-scans the complete event log.

## Availability Semantics

* Full-day call counts use stage response artifacts.
* Latency uses only the recent bounded event window and reports coverage.
* Missing token or cost fields are `UNAVAILABLE`, never zero.
* A configured model without a selected-day artifact is `CONFIGURED`, not used.
* The trade-report MiniMax runtime path versus Nemotron generic-router default
  is exposed as `ROUTING_WARNING` until the code paths are reconciled.

## Web Surface

The ninth product page, `LLM Operations`, includes:

* daily call count, success rate, average and P95 recent latency;
* role-level configured and observed model table;
* Strategist stage call chart and detail table;
* recent sanitized OpenRouter call rows;
* token/cost availability and routing-integrity warnings.

The page remains operational rather than evaluation-progress oriented.

## Verification

```text
Focused LLM API and isolation tests: 9 passed
API plus existing operator UI regression: 100 passed, 1 skipped
Web unit tests: 3 passed
Web TypeScript and production build: passed
Browser smoke: 18 desktop/mobile route renders passed
Console/page errors: 0
Horizontal document overflow: 0
Chart SVG bars: non-zero pixel width verified
```

Live read-only endpoint verification on 2026-08-14 observed:

```text
status: PARTIAL
calls: 79
success: 79
Strategist stage 1: 2
Strategist stage 2: 77
observed model: deepseek/deepseek-v3.2
```

`PARTIAL` is expected while token/cost fields are absent and latency is a
bounded recent-window measurement.

## Runtime Boundary

Only the independent read-only API was restarted. Web hot reload applied the
new page. Trading Runtime was not restarted or modified.
