# Canonical Event Schema

## Why events are canonical

`data/logs/events.jsonl` is the source of truth for explainability.

The runtime should first record rich strategist, scanner, and monitor events in the
canonical event log. Trade-scoped artifacts are then derived from those events.

That keeps the explainability stack ordered like this:

1. canonical runtime events
2. trade-scoped evidence aggregates
3. trade lifecycle / aggregated execution bundle
4. ai trade report input / operator brief input
5. rendered operator-facing artifacts

## Common event envelope

All events now carry the shared envelope fields:

- `ts`
- `event_name`
- `level`
- `run_id`
- `trade_id`
- `session_id`
- `cycle_id`
- `agent`
- `phase`
- `symbol`
- `payload`

Legacy `stage` and `event` fields are still preserved for compatibility.

## New event types

### Strategist

- `strategist.market_context_snapshot`
- `strategist.global_sentiment_breakdown`
- `strategist.news_evidence_ranked`
- `strategist.decision_frame`
- `strategist.llm_response_saved`

### Scanner

- `scanner.candidate_pool_snapshot`
- `scanner.candidate_ranking_table`
- `scanner.candidate_selection_reason`
- `scanner.selection_output`

### Monitor

- `monitor.threshold_snapshot`
- `monitor.state_transition`
- `monitor.exit_decision_detail`
- `monitor.cycle_summary`

## Trade-scoped evidence artifacts

Under `reports/trades/<date>/<trade_id>/evidence/`:

- `strategist_evidence.json`
- `scanner_evidence.json`
- `monitor_timeline.json`

These are aggregates derived from canonical events for the lifecycle's linked run ids.

## Downstream consumers

The richer evidence is now attached to or referenced from:

- `trade_lifecycle.json`
- `aggregated_execution_bundle.json`
- `ai_trade_report_input.json`
- `brief_input.json`

The event log remains authoritative. These files are convenience views over the
same runtime evidence.
