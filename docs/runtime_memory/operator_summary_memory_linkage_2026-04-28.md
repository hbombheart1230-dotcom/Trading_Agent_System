# Operator Summary Memory Linkage (2026-04-28)

## Purpose

Operator summaries are the curated human-facing memory view.

They should be visible to the strategist and commander diagnostics, but they should not replace the existing runtime memory source used for gates and deterministic bias.

## Source Split

Existing strategy memory remains the behavioral source:

- daily: `reports/performance/<day>/strategy_memory.json`
- weekly/monthly: recent windows of `reports/performance/<day>/strategy_memory.json`
- symbol: selected symbol memory packet and symbol quality gates

Operator summaries are supplemental:

- daily: `reports/operator_summary/daily/<YYYY-MM-DD>/daily_summary.json`
- weekly: `reports/operator_summary/weekly/<YYYY-Www>/weekly_summary.json`
- monthly: `reports/operator_summary/monthly/<YYYY-MM>/monthly_summary.json`
- symbol: `reports/operator_summary/symbols/<SYMBOL>/symbol_summary.json`

The two surfaces overlap through underlying trade artifacts, but they are not identical. Do not remove the performance memory source until the operator summary pipeline explicitly becomes the canonical strategy-memory producer.

## Runtime Contract

Each memory packet may include:

```json
{
  "operator_summary": {
    "available": true,
    "status": "ok",
    "layer": "daily",
    "key": "2026-04-28",
    "artifact_path": "reports/operator_summary/daily/2026-04-28/daily_summary.json",
    "metrics": {
      "trade_count": 9,
      "closed_trade_count": 8,
      "win_rate": 0.25,
      "avg_return_pct": -0.4
    }
  }
}
```

Missing summaries are represented explicitly:

```json
{
  "available": false,
  "status": "missing",
  "layer": "weekly",
  "key": "2026-W18",
  "artifact_path": "reports/operator_summary/weekly/2026-W18/weekly_summary.json"
}
```

## Behavior Rules

- Summary presence is quality/visibility evidence only.
- Summary presence must not activate daily/weekly/monthly/symbol memory by itself.
- Scanner and monitor memory bias still depend on commander memory policy, sample quality, recency, and symbol override gates.
- The strategist compact payload preserves `operator_summary` intact because this JSON is already curated and bounded.
- `memory_usage_trace` and `memory_packet_visibility` expose whether the summary was available and where it came from.
- Daily operator summary generation also syncs `reports/performance/<day>/summary.json`, `playbook_stats.json`, `symbol_stats.json`, and `strategy_memory.json`.
- The synced `strategy_memory.json` is the behavioral daily/weekly/monthly memory source used by commander gates.
- `strategy_memory.json` records playbook-level performance and pattern-level performance separately.
- Pattern-level memory is currently advisory/visibility only; it should not change scanner or monitor behavior until explicitly wired through commander policy.

## Current Implementation

- `libs/runtime/operator_summary_memory.py` resolves and loads the summary artifacts.
- `daily_strategy_memory_packet`, `weekly_strategy_memory_packet`, `monthly_strategy_memory_packet`, and `symbol_memory_packet` attach `operator_summary`.
- `commander_memory_policy` surfaces summary metrics in `layer_quality`.
- `strategist_packet_visibility` and `strategist_explanation` surface summary availability/path/metrics.
- `strategist_node` keeps `operator_summary` in the compact LLM payload instead of trimming it away.
- `libs/performance/strategy_memory.py::sync_strategy_memory_artifacts` writes the performance memory artifacts.
- `libs/reporting/operator_period_summary.py::generate_operator_daily_summary_artifact` calls that sync after daily summary payload construction.
- `libs/performance/performance_aggregator.py` records entry pattern, exit pattern, entry reason, exit reason, and entry-exit combo stats.
- `strategy_memory.json` exposes those stats as `pattern_performance_snapshot`.

## Pattern Memory Shape

`pattern_performance_snapshot` keeps the playbook frame from becoming too coarse.

Example:

```json
{
  "pattern_performance_snapshot": {
    "entry_pattern_types": {
      "breakout": {"trade_count": 14, "win_rate": 0.0, "avg_return": -0.007405}
    },
    "exit_pattern_types": {
      "peak_drawdown": {"trade_count": 15, "win_rate": 0.0, "avg_return": -0.006322}
    },
    "entry_exit_combos": {
      "breakout -> peak_drawdown": {"trade_count": 11, "win_rate": 0.0, "avg_return": -0.0061}
    },
    "problem_patterns": ["entry_exit:breakout->peak_drawdown"],
    "working_patterns": []
  }
}
```

The point is to preserve the distinction between:

- `defensive playbook underperformed`
- `defensive frame repeatedly entered breakout patterns and exited through peak_drawdown`

The second form is the useful memory for future commander/monitor tuning.

## Validation

Current targeted tests:

- `tests/test_operator_summary_memory_linkage.py`
- `tests/test_daily_strategy_memory_packet.py`
- `tests/test_commander_memory_policy.py`
- `tests/test_strategist_frame_llm_integration.py::test_build_compact_strategist_llm_payload_trims_memory_and_news`
- `tests/test_strategist_explanation_contract.py`
- `tests/test_operator_summary_reports.py`
