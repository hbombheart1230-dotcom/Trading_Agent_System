# Strategist Memory Packet Visibility (2026-04-20)

## Goal
This document fixes one practical confusion:

- report-derived memory packets **do** flow into Strategist
- but they are **not** visible in `ai_trade_report.md`
- and they are **not always** preserved in the same shape across every runtime artifact

The purpose here is to state:

1. which file is the primary proof
2. which file is only a normalized summary
3. how `selected_symbol_memory` should look when absent vs present

## Direct Answer
`ai_trade_report.md` is **not** the verification surface for Strategist input.

Why:

- `reports/trades/<day>/<trade_id>/reports/ai_trade_report.md` is a post-trade retrospective report
- it is produced by the report lane
- it narrates the trade lifecycle for operator/report consumption
- it does **not** carry Strategist prompt packets such as:
  - `read_model_facts`
  - `recent_strategy_feedback`
  - `reporter_feedback_packet`
  - `strategy_memory`
  - `selected_symbol_memory`

If the question is "did the report-derived memory packet actually reach Strategist?", the first file to inspect is:

- `reports/llm/<day>/<run_id>/strategist/prompt.json`

## Verification Surfaces

### 1. Full Prompt Payload Proof
Use:

- `reports/llm/<day>/<run_id>/strategist/prompt.json`

This is the primary proof because it stores the actual payload sent into the Strategist LLM builder.

The packet keys should be visible directly under:

- `payload.read_model_facts`
- `payload.recent_strategy_feedback`
- `payload.reporter_feedback_packet`
- `payload.strategy_memory`
- `payload.commander_refresh_context.selected_symbol_memory`

### 2. Normalized Canonical Strategist Proof
Use:

- `reports/canonical/<day>/<run_id>/strategist.json`

This is still useful, but it is **not** the full prompt payload.
It stores a normalized Strategist output surface.

What is usually visible there:

- `decision_frame.strategy_memory`
- `decision_frame.reporter_feedback_packet`
- `commander_refresh_context`
- `memory_packet_visibility`
- `llm_trace_refs.prompt_ref`

What is often **not** preserved there in the same full shape:

- full `read_model_facts`
- full `recent_strategy_feedback`
- full `selected_symbol_memory`

So:

- `prompt.json` = full input proof
- `strategist.json` = normalized decision/output proof
- `strategist.json.memory_packet_visibility` = compact packet presence/status proof

## New Compact Visibility Surface

`reports/canonical/<day>/<run_id>/strategist.json` now includes:

- `memory_packet_visibility.read_model_facts`
- `memory_packet_visibility.recent_strategy_feedback`
- `memory_packet_visibility.reporter_feedback_packet`
- `memory_packet_visibility.strategy_memory`
- `memory_packet_visibility.selected_symbol_memory`
- `memory_packet_visibility.commander_refresh_context`

This surface is intentionally compact.

It is meant to answer:

- did the packet reach Strategist?
- was it empty or populated?
- what was the selected symbol / refresh reason?

It is **not** meant to replace `prompt.json` as the full payload proof.

## Today Live Example: Report Packets Did Reach Strategist

Current live example:

- `reports/llm/2026-04-20/f06b58710f2c41b7b0c01d6488eae76d/strategist/prompt.json`

Observed there:

1. `payload.recent_strategy_feedback`
- `feedback_window_size = 12`
- `suggested_report_focus = ["exit_quality", "scanner_fit", "guard_blocks", "overtrading"]`
- `top_recent_weaknesses` populated

2. `payload.read_model_facts`
- `recent_trades` present
- `symbol_patterns` present

3. `payload.strategy_memory`
- key is present
- current example value:
  - `status = "empty"`

4. `payload.reporter_feedback_packet`
- key is present
- current example value:
  - `available = false`
  - `status = "auto_ignored"`

This means:

- the packet wiring is present
- but the report-side availability for this cycle was limited
- "empty" or "auto_ignored" is still a valid packet flow state

## Today Live Example: No Prior Symbol History

Current selected-symbol refresh example:

- `reports/llm/2026-04-20/97394155924e45c98cc772cb83ee164b/strategist/prompt.json`

Observed there:

- `payload.commander_refresh_context.selected_symbol = "356680"`
- `payload.commander_refresh_context.selected_symbol_memory = {}`

Also confirmed:

- `payload.read_model_facts.symbol_patterns` does **not** contain `356680`

Interpretation:

- the symbol was selected
- the refresh path ran
- but there was no prior trade-history-derived symbol memory for that ticker

This is the correct empty-state behavior.

## Expected Contract: Empty vs Populated Symbol Memory

### Empty state
When there is no prior trade history for the selected symbol:

```json
{
  "commander_refresh_context": {
    "selected_symbol": "356680",
    "selected_symbol_memory": {}
  }
}
```

This means:

- no prior symbol history exists
- no symbol-memory bias should be assumed
- the Strategist should rely on:
  - `read_model_facts`
  - `recent_strategy_feedback`
  - `reporter_feedback_packet`
  - `strategy_memory`
  - current refresh context

### Populated state
When prior history exists, `selected_symbol_memory` should be present under the same path.

Test-backed populated example shape:

- `tests/test_strategist_frame_llm_integration.py:876`
- `tests/test_data_quality_state_propagation.py:188`

Example shape:

```json
{
  "commander_refresh_context": {
    "selected_symbol": "000660",
    "selected_symbol_memory": {
      "symbol": "000660",
      "trade_count": 9,
      "win_rate": 0.4444,
      "dominant_playbook": "pullback",
      "dominant_monitor_blocker": "below_vwap_reclaim_not_ready"
    }
  }
}
```

This is the visibility contract we want in live artifacts as well:

- no history -> `{}`
- history exists -> compact symbol-memory excerpt

## Why `ai_trade_report.md` Does Not Show This

`ai_trade_report.md` is downstream from:

- `trade_story_pipeline.py`
- `trade_read_model.py`
- `trade_report_ai.py`

That file is meant to explain:

- market context
- selection rationale
- holding story
- exit decision

It is **not** meant to mirror the upstream Strategist prompt packet.

So if someone tries to verify:

- "did `recent_strategy_feedback` reach Strategist?"
- "did `selected_symbol_memory` reach Strategist?"

the answer is:

- do **not** inspect `ai_trade_report.md`
- inspect `reports/llm/<day>/<run_id>/strategist/prompt.json`

## Runtime Gap Found On 2026-04-20

During live inspection on `2026-04-20`, there was a concrete gap:

- some Commander runs ended with:
  - `selected_route = cached_strategist`
  - `strategist_refresh_requested = true`
  - `strategist_refresh_reason = selected_symbol_outside_cached_frame`
- but those same runs had no matching:
  - `reports/canonical/<day>/<run_id>/strategist.json`
  - `reports/llm/<day>/<run_id>/strategist/prompt.json`

Observed examples:

- `f22ed6db85134df8b482cbdb127b7d87`
- `efe32dffad7848a28b7935a39a4b9b5a`
- `cdd7dc29b77f495fad61aef6af7d87b2`

Root cause:

- this was not a packet-wiring problem

## New Report Surface

`ai_trade_report` now exposes strategist memory usage directly.

JSON surface:

- `reports/trades/<day>/<trade_id>/reports/ai_trade_report.json`
  - `memory_surface.status`
  - `memory_surface.strategy_memory`
  - `memory_surface.selected_symbol_memory`
  - `memory_surface.reporter_feedback_packet`
  - `memory_surface.read_model_facts`
  - `memory_surface.usage_trace`

Markdown surface:

- `reports/trades/<day>/<trade_id>/reports/ai_trade_report.md`
  - `## 메모리 사용`

This surface is meant to answer:

- which memory packets were actually present
- which packets were empty or unavailable
- whether the selected-symbol memory was populated
- how strategist output reflected those packets in:
  - `playbook`
  - `monitor_guidance`
  - `scanner_bias`

Important constraint:

- `strategy_memory` is currently shown as an aggregated packet
- the report explicitly states that daily/weekly/monthly memory is **not** split into separate strategist packets yet
- it was a **post-scanner refresh orchestration gap**
- the scanner selected a symbol outside the cached strategist frame
- Commander marked `RUN_REFRESH`
- but the integrated chain still finished on the cached strategist path

Code status:

- this gap has now been patched in `graphs/commander_runtime.py`
- current expected behavior is:
  1. cached strategist frame may be used for the first scanner pass
  2. if scanner selects a symbol outside the cached frame
  3. Strategist is rerun
  4. scanner is rerun
  5. fresh strategist artifacts should then be persisted

Validation status:

- targeted regression test added:
  - `tests/test_m21_commander_runtime_entry.py::test_m31_integrated_chain_reruns_strategist_after_scanner_when_cached_frame_symbol_mismatch`
- live runtime still needs a restart-and-observe cycle to confirm new artifact persistence in production artifacts

## 2026-04-20 Post-Market Artifact Validation

After reloading today's strategist artifacts with current loaders:

- sampled strategist artifacts: `46`
- `strategy_memory.status = "ok"`: `46`
- `reporter_feedback_packet.available = true`: `45`
- `reporter_feedback_packet.consumed = true`: `45`
- `reporter_feedback_packet.source_available = true`: `45`
- `reporter_feedback_packet.feedback_gate_reason = "auto_accepted"`: `45`
- `selected_symbol_memory.symbol != ""`: `31`
- `selected_symbol_memory.present = true`: `26`
- `selected_symbol_memory.empty_state = true`: `5`

Interpretation:

- packet wiring is broadly present
- `strategy_memory` now resolves through latest-available-day fallback instead of collapsing to same-day empty state
- `reporter_feedback_packet` now resolves directly from same-day metrics when no state packet is attached yet for almost every sampled strategist artifact
- `selected_symbol_memory` now populates from persisted symbol artifacts even when the selected symbol is outside `read_model_facts.symbol_patterns`
- the remaining `empty_state = true` cases were `069540` runs where persisted symbol files existed but `trade_count = 0`, so empty-state behavior remained correct

## Strategy Memory Fallback Update

`strategy_memory` was persistently empty on `2026-04-20` not because the packet schema was wrong, but because the loader was reading the requested day only.

Current behavior after the patch in `libs/performance/strategy_memory.py`:

- if the requested day has no `reports/performance/<day>/strategy_memory.json`
- and auto-build is disabled
- Strategist now falls back to the latest available performance day

Repository check after the patch:

- requested day: `2026-04-20`
- resolved day: `2026-04-17`
- loaded status: `ok`
- example `best_playbooks`: `["defensive"]`

New loader observability:

- `strategy_memory.day` = resolved source day
- `strategy_memory.requested_day` = originally requested day
- `strategy_memory.resolved_day` = fallback day actually used

This means future Strategist runs should no longer surface `strategy_memory.status = "empty"` simply because there was no same-day performance artifact yet.

## Reporter Feedback Fallback Update

`reporter_feedback_packet.available = false` was also not a schema problem.

Root cause:

- intraday Strategist runs usually do not have a closeout reporter hook packet already attached to state
- `_load_reporter_feedback_packet(...)` was effectively waiting for `state["strategist_feedback_packet"]` or `state["reporter_feedback_packet"]`
- even though `reports/metrics/<day>.json` already existed and was enough to build a deterministic advisory packet

Current behavior after the patch in `graphs/nodes/strategist_node.py`:

- if no reporter feedback packet is present on state
- Strategist now builds one directly from `reports_root` + `day`
- source builder: `libs.reporting.reporter_feedback.build_strategist_feedback_packet(...)`

Repository check after the patch:

- day: `2026-04-20`
- `reports/metrics/metrics_2026-04-20.json`: present
- derived packet `available = true`
- derived packet `confidence = "high"`
- derived `monitor_only_ratio = 0.431`
- top recommendation includes:
  - `Cached strategist reuse is elevated; compare refresh cadence against fresh full-cycle opportunities.`

This means future Strategist runs should no longer surface `reporter_feedback_packet.status = "auto_ignored"` simply because the packet was missing from state while same-day metrics already existed.
