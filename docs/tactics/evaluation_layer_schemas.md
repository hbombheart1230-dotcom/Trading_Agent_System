# Evaluation Layer Schemas

Purpose: proposed schema contracts for the read-only evaluation bridge.

These schemas are interface targets only. They do not modify execution behavior.

## Module Targets

Planned read-only modules:

- `libs/reporting/trade_read_model.py`
- `libs/reporting/trade_evaluator.py`
- `libs/reporting/scorecard_daily.py`
- `libs/reporting/strategist_feedback.py`

Existing modules with overlapping behavior should be reused or wrapped, not
duplicated.

## Interface Chain

```text
build_trade_read_model(trade_dir) -> TradeReadModel
evaluate_trade(read_model) -> TradeEvaluation
build_daily_scorecard(day, evaluations, operator_summary, broker_snapshot) -> DailyScorecard
build_strategist_feedback(scorecard) -> StrategistFeedback
```

All functions are read-only.

## `trade_read_model`

Schema target: `trade_read_model.v1`

Expected input:

- trade lifecycle bundle
- trade report JSON/markdown
- broker truth snapshot where available
- quant tactic artifacts
- shadow candidate artifacts
- post-exit observation artifacts

Expected output:

```json
{
  "schema_version": "trade_read_model.v1",
  "trade_id": "",
  "day": "",
  "symbol": "",
  "symbol_name": "",
  "trade_dir": "",
  "status": {
    "lifecycle_status": "",
    "broker_status": "",
    "report_status": ""
  },
  "prices": {
    "entry_price": null,
    "exit_price": null,
    "quantity": null,
    "realized_pnl": null,
    "realized_pnl_pct": null,
    "pnl_source": ""
  },
  "entry": {
    "entry_time": "",
    "entry_reason": "",
    "entry_quant_decision": {},
    "cost_floor_state": {},
    "blockers": []
  },
  "exit": {
    "exit_time": "",
    "exit_reason": "",
    "exit_quant_decision": {},
    "post_exit_observation": {}
  },
  "tactic": {
    "quant_tactic_id": "",
    "tactic_suitability": null,
    "pullback_quality": null,
    "volume_quality": null
  },
  "candidate_selection": {
    "top_candidate": {},
    "selected_candidate": {},
    "runner_up_review": {},
    "selection_reason": ""
  },
  "shadow": {
    "candidate_evaluation": {},
    "forward_outcomes": {},
    "coverage_status": ""
  },
  "integrity": {
    "status": "",
    "missing_fields": [],
    "conflicts": [],
    "source_files": []
  }
}
```

## `trade_evaluation`

Schema target: `trade_evaluation.v1`

Expected input:

- one `trade_read_model.v1`

Expected output:

```json
{
  "schema_version": "trade_evaluation.v1",
  "trade_id": "",
  "day": "",
  "symbol": "",
  "evaluation_mode": "read_only",
  "integrity_status": "PASS",
  "pnl_assessment": {
    "realized_pnl_pct": null,
    "cost_adjusted": null,
    "classification": ""
  },
  "entry_quality": {
    "accepted_top_candidate": null,
    "runner_up_used": null,
    "cost_floor_result": "",
    "pullback_quality_result": "",
    "volume_quality_result": "",
    "assessment": ""
  },
  "exit_quality": {
    "exit_reason": "",
    "intraday_low_break_aggressive": null,
    "profit_fade_before_exit": null,
    "post_exit_best_checkpoint": "",
    "assessment": ""
  },
  "tactic_alignment": {
    "quant_tactic_id": "",
    "tactic_suitability": null,
    "matched_actual_quality": null,
    "assessment": ""
  },
  "shadow_comparison": {
    "shadow_candidates_available": null,
    "selected_outperformed_shadow": null,
    "coverage_status": "",
    "assessment": ""
  },
  "defects": [],
  "watch_items": [],
  "evidence_refs": [],
  "feedback_atoms": []
}
```

## `daily_scorecard`

Schema target: `daily_scorecard.v1`

Expected input:

- list of `trade_evaluation.v1`
- operator summary
- broker order/fill snapshot
- quant tactic evaluation summary
- shadow candidate evaluation summary

Expected output:

```json
{
  "schema_version": "daily_scorecard.v1",
  "day": "",
  "generated_at": "",
  "evaluation_mode": "read_only",
  "integrity_rollup": {
    "status": "PASS",
    "broker_trade_count": 0,
    "report_trade_count": 0,
    "missing_report_count": 0,
    "conflict_count": 0
  },
  "performance": {
    "closed_trades": 0,
    "wins": 0,
    "losses": 0,
    "flats": 0,
    "realized_pnl_pct_avg": null,
    "realized_pnl_total": null
  },
  "tactic_scorecards": [],
  "candidate_selection_scorecards": [],
  "exit_scorecards": [],
  "shadow_scorecards": [],
  "validation_questions": {
    "top_candidate_accept_reject": "",
    "runner_up_selection": "",
    "cost_floor_blocking": "",
    "tactic_suitability_match": "",
    "volume_pullback_quality": "",
    "shadow_candidates_inferior": "",
    "intraday_low_break_aggression": "",
    "profit_fade_exits": ""
  },
  "defect_counts": {},
  "watch_items": [],
  "action_candidates": []
}
```

`action_candidates` are advisory only. They are not runtime instructions.

## `strategist_feedback`

Schema target: `strategist_feedback.v1`

Expected input:

- one `daily_scorecard.v1`
- optional recent scorecard window

Expected output:

```json
{
  "schema_version": "strategist_feedback.v1",
  "day": "",
  "behavior_effect": "advisory_only",
  "source_scorecard": "",
  "do_not_change_execution": true,
  "feedback_items": [
    {
      "type": "",
      "scope": "",
      "message": "",
      "evidence": [],
      "confidence": "low"
    }
  ],
  "unanswered_questions": [],
  "not_a_guard": true
}
```

## Authority Boundary

These schemas may feed strategist context after review. They must not directly
change:

- position sizing
- entry permission
- exit permission
- monitor stop logic
- scanner rank
- commander approval
- broker order behavior
