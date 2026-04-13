# Entry Blocker Analysis Read-Model Close

## Why This Was Needed
- Recent live runs showed that the main bottleneck had shifted from exit anomalies to entry quality.
- BUY frequency stayed low and realized outcomes stayed mostly negative, while monitor artifacts repeatedly surfaced entry-side blockers such as:
  - `rebound_ok`
  - `pullback_ok`
  - `pullback_not_mature`
  - `volume_confirmation_missing`
  - `buy_blocked_open_position`
  - `post_exit_cooldown`
- The system already computed much of this evidence internally, but it was still too hard to read at run/day/symbol/time granularity.

## What Was Added

### 1. Normalized Monitor Surface
- A new additive `entry_blocker_surface` is now produced from monitor entry evidence.
- It normalizes the most important entry blockers and guard states into one place:
  - `final_decision`
  - `primary_blockers`
  - `no_trade_code`
  - `entry_style`
  - `rebound_ok`
  - `pullback_ok`
  - `pullback_not_mature`
  - `volume_ok`
  - `volume_confirmation_missing`
  - `structure_hh_hl`
  - `open_position_blocked`
  - `cooldown_blocked`
  - `post_exit_cooldown_remaining_sec`
  - confidence / pullback / volume evidence

### 2. Entry Blocker Read-Model
- New read-model module:
  - `libs/reporting/entry_blocker_read_model.py`
- It reads canonical `monitor.json` and `scanner.json` together and produces a row model that supports:
  - blocker frequency
  - no-trade code frequency
  - symbol-level drilldown
  - time bucket analysis
  - scanner-selected quality vs monitor blocker linkage

### 3. Aggregation Script
- New analysis script:
  - `scripts/analyze_entry_blockers.py`
- Supported inputs:
  - `--date YYYY-MM-DD`
  - `--symbol`
  - `--limit`
- It can print markdown to stdout and optionally save JSON / markdown summaries.

## Read-Model Shape
- Core row fields:
  - `run_id`
  - `ts`
  - `ts_kst`
  - `time_bucket`
  - `symbol`
  - `final_decision`
  - `primary_blockers`
  - `no_trade_code`
  - `entry_style`
  - `confidence_score`
  - `confidence_threshold`
  - `pullback_depth_pct`
  - `rebound_ok`
  - `pullback_ok`
  - `structure_hh_hl`
  - `volume_ok`
  - `volume_confirmation_missing`
  - `open_position_blocked`
  - `cooldown_blocked`
  - `scanner_selected_summary`

## Time Bucket Model
- `open_window`
- `mid_session`
- `late_session`

This is intentionally simple and deterministic so we can first answer:
- Are `pullback_not_mature` waits clustered at the open?
- Is `rebound_ok` mostly failing in specific buckets?
- How much opportunity loss is actually tied to cooldown or open-position blocks?

## Scope Boundary
- This change is analysis-only.
- It does **not**:
  - relax thresholds
  - change pullback / rebound / volume gate semantics
  - change scanner ranking
  - change strategist policy
  - change exit policy

## Remaining Limits
- The read-model improves observability, not trade quality by itself.
- Some older canonical runs may not contain the new `entry_blocker_surface`, so the reader still falls back to existing monitor fields when needed.
- The next step should be blocker interpretation and tuning, not blind gate loosening.
