# Strategist Explanation Contract

Date: 2026-04-25

Status: draft implementation contract

Implementation note:

- 2026-04-25 slice 1 adds deterministic strategist explanation builders.
- `strategist_output` and canonical `strategist.json` now surface the proposed explanation fields.
- `memory_usage_trace` and `news_usage_trace` are deterministic-first; LLM wording may be additive but must not invent active memory layers, gate reasons, or news linkage.
- 2026-04-25 slice 2 strengthens `memory_usage_trace` with per-layer `visible`, `used`, `gate_reason`, `effect`, `application_targets`, plus scanner/monitor memory-bias application summaries.

## Purpose

The strategist output should explain how the strategy frame was built, not just summarize the final playbook.

This contract adds explicit JSON fields for:

- strategy thesis
- strategy changes vs prior frame
- memory usage
- news usage
- scanner handoff
- monitor handoff
- conflict resolution
- trade permission frame

The goal is to make "why no trade happened" and "why this frame was chosen" debuggable without asking the reporter to infer intent from scattered artifacts.

## Role Boundary

The strategist is not responsible for final symbol selection.

Responsibilities:

- interpret market/regime/news/memory context
- choose strategy playbook and risk posture
- define scanner ranking guidance
- define monitor confirmation and hold-off conditions
- explain how deterministic memory/news evidence affected the strategy frame

Not responsible for:

- final symbol selection
- final candidate ranking
- entry execution
- broker order placement
- fill confirmation

The scanner owns final candidate ranking and selected symbol. The monitor owns whether the selected symbol satisfies entry conditions. Executor and supervisor own order execution and permission.

## Proposed Top-Level Fields

Add these fields to `strategist_output` and canonical `strategist.json`:

```json
{
  "strategy_thesis": {},
  "strategy_delta_trace": {},
  "memory_usage_trace": {},
  "news_usage_trace": {},
  "scanner_handoff": {},
  "monitor_handoff": {},
  "conflict_analysis": {},
  "trade_permission_frame": {},
  "responsibility_boundary": {}
}
```

These fields should be additive and backward-compatible. Existing fields such as `strategy_summary`, `strategy_memory`, `reporter_feedback_packet`, `news_evidence_ranked`, `commander_memory_policy`, and `memory_packet_visibility` remain available.

## Field Contract

### `strategy_thesis`

Human-readable explanation of the selected strategy frame.

```json
{
  "market_view": "Theme participation is present, but breakout follow-through is unstable.",
  "trade_style": "Prefer pullback/reclaim confirmation over direct chase.",
  "risk_tone": "balanced_defensive",
  "selected_playbook": "pullback_reclaim",
  "one_line": "Allow candidate search, but require VWAP reclaim and volume confirmation before entry."
}
```

Required properties:

- `market_view`
- `trade_style`
- `risk_tone`
- `selected_playbook`
- `one_line`

### `strategy_delta_trace`

Explains whether the strategist changed the frame compared with the previous usable frame.

```json
{
  "changed": true,
  "previous_playbook": "breakout",
  "current_playbook": "pullback_reclaim",
  "change_reason": "Recent failures are concentrated in extended breakout entries.",
  "unchanged_items": ["theme alignment priority", "liquidity filter"],
  "evidence_refs": ["memory_usage_trace.daily", "conflict_analysis"]
}
```

If no prior frame is available, use:

```json
{
  "changed": false,
  "previous_playbook": "",
  "current_playbook": "breakout",
  "change_reason": "No prior comparable strategist frame was available.",
  "unchanged_items": [],
  "evidence_refs": []
}
```

### `memory_usage_trace`

Explains how daily/weekly/monthly/symbol memory affected the strategy frame.

This is different from `memory_packet_visibility`.

- `memory_packet_visibility`: whether the strategist could see the packet
- `memory_usage_trace`: whether and how the strategist used or ignored the packet

```json
{
  "schema_version": "strategist.memory_usage_trace.v1",
  "active_layers": ["daily", "weekly"],
  "priority_order": ["daily", "weekly", "monthly", "symbol"],
  "layer_decisions": {
    "daily": {
      "status": "ok",
      "active": true,
      "used": true,
      "confidence": 0.83,
      "effect": "tighten_entry_confirmation",
      "reason": "Recent failed trades show too_extended_from_vwap and weak breakout follow-through."
    },
    "weekly": {
      "status": "ok",
      "active": true,
      "used": true,
      "confidence": 0.61,
      "effect": "keep_balanced_defensive_risk_tone",
      "reason": "Weekly source performance is mixed and monitor-only route ratio remains elevated."
    },
    "monthly": {
      "status": "ok",
      "active": false,
      "used": false,
      "confidence": 0.34,
      "effect": "none",
      "reason": "Monthly sample quality is below activation floor."
    },
    "symbol": {
      "status": "ok",
      "active": true,
      "used": false,
      "confidence": 0.0,
      "effect": "none",
      "gate_reason": "insufficient_trade_count",
      "reason": "Symbol memory exists but is too thin for override."
    }
  },
  "applied_to_strategy": {
    "playbook_effect": "maintain_pullback_reclaim",
    "risk_posture_effect": "balanced_defensive",
    "scanner_guidance_effect": "penalize extended breakout candidates",
    "monitor_policy_effect": "require stronger reclaim and volume confirmation"
  },
  "human_summary": "Daily memory tightened entry confirmation, weekly memory kept the frame defensive, and symbol memory was visible but not used because the sample was too thin."
}
```

Rules:

- Always include every available layer decision.
- `used=false` is required when a layer is visible but not applied.
- Include `gate_reason` for symbol memory when not used.
- Do not claim symbol memory changed final symbol selection.
- Effects must point to strategy frame, scanner guidance, or monitor policy only.

### `news_usage_trace`

Explains how news affected the strategy frame.

```json
{
  "schema_version": "strategist.news_usage_trace.v1",
  "query_targets": ["KOSPI", "semiconductor", "battery"],
  "market_headlines_used": ["KOSPI foreign/institution buying strengthened"],
  "candidate_headlines_used": ["Semiconductor demand recovery expectations"],
  "market_effect": "supports selective risk-on, but not enough to chase extended moves",
  "playbook_effect": "kept pullback/reclaim frame instead of pure breakout",
  "scanner_guidance_effect": "prefer candidates with theme/news alignment only when tape confirms",
  "monitor_policy_effect": "news does not relax entry gate without volume/VWAP confirmation",
  "ignored_or_low_signal_news": ["generic macro headlines without candidate linkage"],
  "confidence": "medium",
  "source_event": "strategist.news_evidence_ranked",
  "human_summary": "News supported theme participation, but the strategist used it as context for selective search rather than as permission to chase entries."
}
```

Rules:

- News may support market tone or theme alignment.
- News must not be described as final symbol selection.
- If headlines are weak or generic, explicitly record that they were low-signal.
- Reporter should prefer this field over reconstructing news usage from raw headlines.

### `scanner_handoff`

Guidance passed to scanner ranking. This is not a selected-symbol explanation.

```json
{
  "prefer_candidate_traits": ["theme alignment", "VWAP support", "rising trading value"],
  "penalize_traits": ["extended candle after news", "weak liquidity", "theme mismatch"],
  "disqualifiers": ["insufficient liquidity", "blocked by risk policy"],
  "ranking_guidance": "Prefer theme-aligned candidates with tape confirmation; penalize news-only momentum without volume confirmation.",
  "not_responsible_for": ["final_symbol_selection", "final_candidate_rank"]
}
```

Rules:

- Use ranking language, not selection ownership language.
- Avoid phrases like "selected because" in strategist output.
- Scanner/reporting may later connect the strategist frame to the selected symbol, but that linkage belongs to scanner/report artifacts.

### `monitor_handoff`

Guidance passed to monitor for entry/hold-off behavior.

```json
{
  "entry_confirmation": ["VWAP reclaim", "volume ratio confirms", "spread stable"],
  "hold_off_conditions": ["too_extended_from_vwap", "breakout_without_volume", "negative tape divergence"],
  "entry_aggressiveness": "normal_to_conservative",
  "recheck_interval_reason": "Wait for confirmation instead of chasing the first breakout candle.",
  "policy_effect_summary": "Entry is allowed only after reclaim and volume confirmation."
}
```

Rules:

- This field explains entry permission conditions, not order execution.
- It should make no-trade periods easier to debug.
- If monitor blocks entry, reporter should compare block reason with this handoff.

### `conflict_analysis`

Shows bullish and bearish evidence together and explains the resolution.

```json
{
  "bullish_evidence": ["theme news increased", "trading value expanded"],
  "bearish_evidence": ["recent extended breakout failures", "market sentiment neutral"],
  "resolution": "Allow candidate search, but tighten monitor confirmation.",
  "confidence": "medium",
  "evidence_refs": ["news_usage_trace", "memory_usage_trace.daily"]
}
```

Rules:

- Always record both sides when mixed evidence exists.
- Resolution must map to strategy, scanner guidance, or monitor guidance.
- Do not hide bearish evidence just because the final frame allows candidate search.

### `trade_permission_frame`

Explains what the strategist permits before scanner/monitor/executor act.

```json
{
  "candidate_search_allowed": true,
  "entry_allowed_if": ["VWAP reclaim confirmed", "volume confirms", "risk policy allows"],
  "entry_blocked_if": ["extension persists", "news is not confirmed by tape", "monitor risk gate fails"],
  "reason": "The strategy allows scanning but does not allow immediate entry without confirmation.",
  "permission_level": "conditional"
}
```

Rules:

- This field should make it clear whether no-trade behavior is expected by strategy.
- `permission_level` should be one of: `open`, `conditional`, `defensive`, `blocked`.
- It must not bypass scanner, monitor, supervisor, or executor.

### `responsibility_boundary`

Explicit ownership statement to prevent report drift.

```json
{
  "strategist_owns": ["market_regime", "risk_posture", "playbook", "scanner_guidance", "monitor_guidance"],
  "scanner_owns": ["candidate_ranking", "selected_symbol"],
  "monitor_owns": ["entry_condition_check", "hold_off_reason", "exit_trigger_observation"],
  "executor_supervisor_owns": ["order_permission", "broker_execution", "fill_confirmation"],
  "not_responsible_for": ["final_symbol_selection", "order_execution"]
}
```

## Reporter Usage

### Direct Consumption Rule

Reporter and operator UI must treat strategist explanation fields as the primary source for strategist reasoning.

Reporter may render, translate, shorten, or reorder the strategist explanation for readability, but it must not invent a different strategist rationale from raw market/news/memory artifacts when the structured strategist fields are present.

In other words:

- use `strategy_thesis` as the strategist's strategy explanation
- use `memory_usage_trace` as the strategist's memory-use explanation
- use `news_usage_trace` as the strategist's news-use explanation
- use `scanner_handoff` as the strategist-to-scanner handoff explanation
- use `monitor_handoff` as the strategist-to-monitor handoff explanation
- use fallback reconstruction only when the corresponding strategist field is missing

This keeps the report from becoming a second strategist. The reporter explains the recorded strategist output; it does not re-decide the strategy.

Reporter and operator UI should prefer these fields in this order:

1. `strategy_thesis`
2. `strategy_delta_trace`
3. `memory_usage_trace`
4. `news_usage_trace`
5. `scanner_handoff`
6. `monitor_handoff`
7. `conflict_analysis`
8. `trade_permission_frame`

Reporter wording rules:

- Say "the strategist framed scanner ranking around ..." instead of "the strategist selected ..."
- Say "news supported/limited the strategy frame ..." instead of "news selected the symbol ..."
- Say "memory tightened/maintained/relaxed the strategy frame ..." instead of "memory forced a trade ..."
- If `used=false`, explicitly explain why the evidence was not applied.

## Artifact Path Targets

These fields should be persisted in:

- canonical strategist artifact: `reports/canonical/<day>/<run_id>/strategist.json`
- strategist LLM response parsed output when LLM mode is active
- live execution bundle strategist summary
- `agent_pipeline_trace`
- `ai_trade_report_input.json`
- final `ai_trade_report.json` and rendered markdown

## Implementation Order

1. Add deterministic builders for `memory_usage_trace` and `news_usage_trace` from existing packet/event data.
2. Extend strategist LLM schema/prompt to produce `strategy_thesis`, `strategy_delta_trace`, `scanner_handoff`, `monitor_handoff`, `conflict_analysis`, and `trade_permission_frame`.
3. Add deterministic fallback values when LLM is disabled, blocked, or malformed.
4. Persist fields into canonical `strategist.json`.
5. Teach trade story pipeline and AI reporter to consume these fields directly.
6. Add regression tests for:
   - strategist output contains responsibility boundary
   - visible but unused memory records `used=false`
   - news usage explains market/theme effect without claiming symbol selection
   - scanner handoff never claims final selection ownership
   - reporter renders memory/news usage in strategist summary

## Open Design Notes

- `memory_usage_trace` should be deterministic-first. The LLM can add wording, but it should not invent active layers or gate reasons.
- `news_usage_trace` should use `strategist.news_evidence_ranked` as the source event.
- Symbol memory should remain gated until data quality is sufficient. Thin symbol memory should be visible but not strategy-changing.
- This contract improves observability and explanation quality. It does not lower thresholds or force more trades.
