# Agent Visibility Runbook (M31+)

- Last updated: 2026-03-06
- Purpose: make current runtime scope and observability sources explicit for day-to-day operations.

## 1) Important Distinction: Runtime Path

1. `scripts/run_m13_live_loop.py` (current live/mock session path)
- Uses `graphs/pipelines/m13_live_loop.py` -> `m13_tick` -> `m10_live_pipeline`.
- Focuses on decision/execution loop.
- In practice, event stages are mostly:
  - `strategist_llm`
  - `decision`
  - `execute_from_packet`

2. `integrated_chain` probe/runtime
- Validates full chain presence:
  - `commander_router -> strategist -> scanner -> monitor -> decision -> supervisor -> executor -> reporter`
- Command:
```bash
python -m scripts.run_m31_agent_chain_probe --json
```

## 2) 7-Agent Status Snapshot (2026-03-06)

1. Full chain wiring exists: `PASS`
- Evidence: `scripts/run_m31_agent_chain_probe.py` returns `ok=true` with full chain list.

2. Session event observability in `run_m13_live_loop`: `PARTIAL`
- `data/logs/events.jsonl` day stats (2026-03-06):
  - `execute_from_packet=786`
  - `decision=313`
  - `strategist_llm=277`
- Commander/scanner/monitor/supervisor/reporter are not continuously emitted in this path by default.

## 3) Is `events.jsonl` Alone Enough?

No. Use a minimum 4-source bundle:

1. `data/logs/events.jsonl`
- decision trace, LLM result, execution verdict/execution, errors.

2. `data/logs/intents.jsonl`
- intent lifecycle/idempotency history (`created/approved/executed/rejected`).

3. `data/state.json`
- cash/positions/pnl/open position state snapshot.

4. `reports/daily/*.md` and `reports/metrics/*.md`
- daily close summary and metric trend artifacts.

Optional:

5. Broker-side evidence
- mock/real broker order ids, account app, or external broker logs.

## 4) What to Check After Market Close

1. Throughput and action mix
- `NOOP/BUY/SELL` distribution from `decision::trace`.

2. Guard and execution quality
- `approved/blocked/executed` counts.
- top block reasons (e.g., `noop_intent_skipped`).

3. Strategist LLM health
- `success_rate`, `latency p95`, `TimeoutError/URLError`, `circuit_open_rate`.

4. Strategy rationale quality
- `query_trade_reason_chain` to confirm:
  - LLM reason
  - decision rationale
  - execution order metadata

5. End-of-day account state
- `open_positions`, `mock_realized_pnl`, `last_execution_reason`.

## 5) Daily Operator Commands (Reference)

```bash
python -m scripts.query_strategist_llm_events --path data/logs/events.jsonl --limit 20
python -m scripts.query_trade_reason_chain --path data/logs/events.jsonl --only-broker-success --limit 20
python -m scripts.run_trade_explain_report --event-log-path data/logs/events.jsonl --report-dir reports/trade_explain --day 2026-03-10 --json
python -m scripts.run_reporter_analysis_report --event-log-path data/logs/events.jsonl --intents-path data/logs/intents.jsonl --report-dir reports/reporter_analysis --day 2026-03-10 --json

set EVENT_LOG_PATH=./data/logs/events.jsonl
set REPORT_DAY=2026-03-06
python -m scripts.generate_daily_report

set EVENT_LOG_PATH=./data/logs/events.jsonl
set METRICS_DAY=2026-03-06
python -m scripts.generate_metrics_report
```

## 6) Trade Explain Report

- Output:
  - `reports/trade_explain/trade_explain_<day>.md`
  - `reports/trade_explain/trade_explain_<day>.json`
- Purpose:
  - Show BUY/SELL execution timeline with reason chain.
  - Build FIFO sell-pair analysis (hold duration + estimated realized PnL).
  - Surface scanner/monitor/decision context in one place.
- Known data gap:
  - Raw news headline text and scanner `score_breakdown` depend on current event payload policy and may be missing.

## 7) Reporter Analysis Report

- Output:
  - `reports/reporter_analysis/reporter_analysis_<day>.md`
  - `reports/reporter_analysis/reporter_analysis_<day>.json`
- Purpose:
  - Integrate trade/intent/operator reports into one passive post-run analysis bundle.
  - Provide overtrading diagnostics and incident/post-mortem summaries.
- Includes:
  - `trade_summary` (trade count, symbols traded, hold-duration table)
  - `decision_chains` (run_id-level decision->supervisor->execution flow)
  - Trade decision summary (buy/sell reasons, hold duration, exit trigger)
  - `strategist_evaluation` (themes vs scanner leader evidence)
  - `scanner_evaluation` (selection appropriateness and candidate pool quality)
  - `monitor_evaluation` (overtrading/guard behavior)
  - `supervisor_activity` (block/approve frequency and top block reasons)
  - Intent flow (`created/blocked/approved/executed`)
  - Strategy effectiveness narrative (Strategist -> Scanner -> Monitor)
  - incidents + improvement suggestions for next run
