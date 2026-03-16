# Agent Visibility Runbook (M31+)

- Last updated: 2026-03-16
- Purpose: make current runtime scope and observability sources explicit for day-to-day operations.

## 1) Important Distinction: Runtime Path

1. `scripts/run_m13_live_loop.py` (current live/mock session path)
- Supports:
  - `legacy_m10`
  - `integrated_chain`
- Current operating baseline should be treated as `integrated_chain` unless explicitly overridden.
- `integrated_chain` emits the full chain:
  - `commander_router -> strategist -> scanner -> monitor -> decision -> supervisor -> executor -> reporter`
- Scanner-side feature hydration is now part of the integrated chain, so session visibility should include:
  - feature coverage
  - hydrated quote metrics
  - candidate source mix

2. `integrated_chain` probe/runtime
- Validates full chain presence:
  - `commander_router -> strategist -> scanner -> monitor -> decision -> supervisor -> executor -> reporter`
- Command:
```bash
python -m scripts.run_m31_agent_chain_probe --json
```

## 2) Current Visibility Snapshot (2026-03-16)

1. Full chain wiring exists: `PASS`
- Evidence: `scripts/run_m31_agent_chain_probe.py` returns `ok=true` with full chain list.

2. Session event observability in `integrated_chain`: `GOOD`
- Operators should expect continuous visibility for:
  - `commander_router`
  - `strategist`
  - `scanner`
  - `monitor`
  - `decision`
  - `supervisor`
  - `executor`
- Reporter remains primarily post-run / reporting-layer output, but same-day operator UI summaries are available during session.

## 3) Is `events.jsonl` Alone Enough?

No. Use a core observability bundle:

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

6. `data/strategy_memory/daily/*.json`
- deduped latest Reporter memory snapshots consumed by Strategist.

7. Operator UI
- `http://127.0.0.1:8010/`
- use for same-day overview, recent runs, feature coverage, quote metrics, and operator briefs.

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

## 5) What to Check During Session

1. `/runs`
- confirm recent cycles keep arriving
- check `macro stress`
- check `feature coverage`

2. `/runs/{run_id}`
- confirm operator brief is populated
- confirm scanner `Feature Coverage` and `Quote Metrics`
- confirm same-day symbol history / recent same-symbol run chain

3. Overview
- `Today Trades`
- `Today Traded Symbols`
- `Overtrading Warning`
- `Latest Strategist Prompt`
- `Strategy Memory Timeline`

## 6) Daily Operator Commands (Reference)

```bash
python -m scripts.query_strategist_llm_events --path data/logs/events.jsonl --limit 20
python -m scripts.query_trade_reason_chain --path data/logs/events.jsonl --only-broker-success --limit 20
python -m scripts.run_trade_explain_report --event-log-path data/logs/events.jsonl --report-dir reports/dev/analysis/trade_explain --day 2026-03-10 --json
python -m scripts.run_reporter_analysis_report --event-log-path data/logs/events.jsonl --intents-path data/logs/intents.jsonl --report-dir reports/dev/analysis/reporter_analysis --day 2026-03-10 --json
python -m scripts.run_reporter_analysis_report --event-log-path data/logs/events.jsonl --intents-path data/logs/intents.jsonl --report-dir reports/dev/analysis/reporter_analysis --day 2026-03-10 --ai-review --json
python -m scripts.run_agent_pipeline_trace_report --event-log-path data/logs/events.jsonl --evidence-log-path data/evidence_ledger/events.jsonl --report-dir reports/dev/analysis/agent_pipeline_trace --day 2026-03-10 --json
python -m scripts.run_offhours_full_trace_bundle --env-path .env --state-path data/state/offhours_full_trace.json --event-log-path data/logs/dev/analysis/offhours/offhours_full_trace.jsonl --evidence-log-path data/evidence_ledger/offhours_full_trace.jsonl --report-dir reports/dev/analysis/offhours_full_trace --json
python -m scripts.run_report_maintenance --report-root reports --event-log-path data/logs/events.jsonl --json
powershell -ExecutionPolicy Bypass -File scripts/start_operator_ui.ps1
powershell -ExecutionPolicy Bypass -File scripts/stop_operator_ui.ps1

set EVENT_LOG_PATH=./data/logs/events.jsonl
set REPORT_DAY=2026-03-06
python -m scripts.generate_daily_report

set EVENT_LOG_PATH=./data/logs/events.jsonl
set METRICS_DAY=2026-03-06
python -m scripts.generate_metrics_report
```

## 7) Trade Explain Report

- Output:
  - `reports/dev/analysis/trade_explain/trade_explain_<day>.md`
  - `reports/dev/analysis/trade_explain/trade_explain_<day>.json`
- Purpose:
  - Show BUY/SELL execution timeline with reason chain.
  - Build FIFO sell-pair analysis (hold duration + estimated realized PnL).
  - Surface scanner/monitor/decision context in one place.
- Known data gap:
  - Raw news headline text and scanner `score_breakdown` depend on current event payload policy and may be missing.

## 8) Reporter Analysis Report

- Output:
  - `reports/dev/analysis/reporter_analysis/reporter_analysis_<day>.md`
  - `reports/dev/analysis/reporter_analysis/reporter_analysis_<day>.json`
- Purpose:
  - Integrate trade/intent/operator reports into one passive post-run analysis bundle.
  - Provide overtrading diagnostics and incident/post-mortem summaries.
  - Optional second-stage AI interpretation over deterministic outputs (post-run/read-only).
- Includes:
  - `trade_summary` (trade count, symbols traded, hold-duration table)
  - `decision_chains` (run_id-level decision->supervisor->execution flow)
  - `decision_trace_chain_summary` (per-run strategist/scanner/monitor/supervisor/executor chain status)
  - Trade decision summary (buy/sell reasons, hold duration, exit trigger)
  - `strategist_evaluation` (themes vs scanner leader evidence)
  - `scanner_evaluation` (selection appropriateness and candidate pool quality)
  - `monitor_evaluation` (overtrading/guard behavior)
  - `supervisor_activity` (block/approve frequency and top block reasons)
  - Intent flow (`created/blocked/approved/executed`)
  - Strategy effectiveness narrative (Strategist -> Scanner -> Monitor)
  - `operator_facing_summary` + `developer_facing_summary`
  - incidents + improvement suggestions for next run
  - optional AI review:
    - `ai_summary`, `ai_findings`, `ai_root_causes`
    - `ai_improvement_suggestions`, `ai_run_grade`, `ai_agent_evaluations`

## 9) Single-Run Agent Pipeline Trace

- Output:
  - `reports/dev/analysis/agent_pipeline_trace/agent_pipeline_trace_<run>.md`
  - `reports/dev/analysis/agent_pipeline_trace/agent_pipeline_trace_<run>.json`
  - `reports/dev/analysis/offhours_full_trace/offhours_full_trace_<run>.md`
  - `reports/dev/analysis/offhours_full_trace/offhours_full_trace_<run>.json`
- Purpose:
  - One-screen trace for all 7 roles:
    - Commander / Strategist / Scanner / Monitor / Supervisor / Executor / Reporter
  - Includes:
    - Strategist news/global-sentiment + LLM prompt/response capture status
    - `news_query_reasoning` explaining why the strategist chose those news query targets
    - Scanner candidate-source mix + top-ranked symbol summary
    - scanner feature hydration / quote metrics when available
    - Monitor entry/exit reasons and sell-guard state
    - Supervisor verdict and Executor broker execution result
  - Sources:
    - `data/logs/events.jsonl`
    - `data/evidence_ledger/events.jsonl`
