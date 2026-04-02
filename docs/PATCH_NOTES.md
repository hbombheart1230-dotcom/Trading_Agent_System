# Phase 1 Patch Notes (Storage Policy + Canonical Artifact Quality)

## What Changed
- Normalized canonical artifact writes remain under `reports/canonical/<day>/<run_id>/`.
- Added normalized LLM raw artifact writer under `reports/llm/<day>/<run_id>/<artifact_name>/`.
- Strategist LLM path now writes:
  - `prompt.json`
  - `response.json`
  - `meta.json`
- Strategist canonical payload now stores only LLM trace refs/hashes/metadata (no raw prompt/response body).
- Scanner canonical payload enhanced with:
  - `candidate_pool_snapshot`
  - `filter_funnel`
  - `selection_reason_detail`
  - `rejection_summary`
- Monitor canonical payload enhanced with:
  - `monitor_evaluation`
  - `monitor_action_decision`
  - clearer triggered/blocked rule visibility
- Artifact schema now includes `day`, and validation tracks required/missing keys and completeness.

## Storage Policy (Phase 1)
- `events.jsonl`: unchanged append-only runtime log.
- `reports/canonical/<YYYY-MM-DD>/<run_id>/`: structured agent artifacts.
- `reports/llm/<YYYY-MM-DD>/<run_id>/`: raw LLM prompt/response artifacts.
- `reports/trades/<YYYY-MM-DD>/<trade_id>/`: trade-level summaries only (no new raw LLM body writes added here in this patch).

## Backward Compatibility Notes
- Legacy read paths were not removed.
- Existing canonical artifact file names are preserved.
- Existing scanner/monitor compatibility fields are preserved; new fields are additive.
- Canonical writer now enforces write-once-per-agent-path in-state to prevent duplicate writes in the same run state object.

## Known Limitations
- Reporter pipeline was intentionally not refactored in this phase.
- Legacy trade/report generation modules may still read old fields; this patch focuses on canonical evidence quality and storage normalization groundwork.

## Phase 2 Addendum (Deterministic-First Reporting)

### What Changed
- Commander artifact was enriched with a decision-frame payload:
  - `session_type`, `market_clock_phase`, `portfolio_state_summary`, `market_regime_summary`
  - `goal`, `agent_invocation_plan`, `decision_checkpoints`
  - `final_runtime_path`, `final_reason`, `handoff_instruction`
- Reporting flow in bundle generation is now deterministic-first:
  1. deterministic report is built/written first
  2. AI trade report generation is attempted second
  3. AI failure no longer blocks report existence
- Added explicit status matrix:
  - `deterministic_report_status`
  - `llm_brief_status`
  - `ai_trade_report_status`
- `_health.json` and `_provenance.json` were expanded with clearer explainability fields:
  - completeness/missing-sections
  - artifact presence map
  - report generation reason
  - read precedence + section resolution metadata
- `_artifact_links.json` now keeps explicit keys (including empty-string refs) and adds LLM prompt/response refs when available.
- Trade/UI read path handling now prefers normalized trade artifacts before fallback paths.

### Deterministic-First Policy
- Deterministic report generation does not depend on LLM availability.
- AI report generation is optional enrichment; failures are recorded without breaking trade-level report outputs.
- `reports/trades` keeps summary artifacts, while raw prompt/response bodies are externalized to `reports/llm` and linked via refs/hashes.

### Status Semantics
- `ok`: complete AI output or deterministic output succeeded.
- `salvaged`: partial AI output recovered with deterministic fallback sections.
- `error`: AI request/parse failure.
- `skipped`: AI generation intentionally skipped by policy/state.

### Backward Compatibility
- Historical artifacts are not deleted or migrated.
- Existing readers can still consume existing files.
- New metadata is additive.

### Remaining Phase 3 Scope
- Broader reporter refactor for fully centralized provenance consumption.
- Wider UI normalization for all report views and sidecar semantics.

## Phase 3 Addendum (Trade-Centric Finalization)

### What Changed
- `reports/trades/<day>/<trade_id>/` is now the operator entrypoint with normalized trade structure.
- Added `lifecycle_bundle.json` as the primary per-trade aggregation artifact.
- Added normalized lifecycle split artifacts:
  - `entry.json`
  - `hold.json`
  - `exit.json`
- Evidence set now explicitly includes:
  - `evidence/strategist_evidence.json`
  - `evidence/scanner_evidence.json`
  - `evidence/monitor_evidence.json`
  - `evidence/commander_evidence.json`
- Trade report outputs moved to `reports/` inside each trade:
  - `reports/operator_brief.json`
  - `reports/operator_brief.md`
  - `reports/ai_trade_report.json`
  - `reports/ai_trade_report.md`
- Trade-scoped LLM artifacts are compact status/ref files only:
  - `reports/strategist_llm_response.json`
  - `reports/brief_llm_response.json`
  - `reports/ai_trade_report_llm_response.json`
  - no raw prompt/response bodies in `reports/trades`
- Added stronger `_artifact_links.json` coverage with explicit keys:
  - canonical refs, lifecycle refs, report refs, llm prompt/response refs
- `_health.json` and `_provenance.json` now reflect Phase 3 completeness axes and source-path clarity.

### Lifecycle Bundle Design
- `lifecycle_bundle.json` includes:
  - `lifecycle.entry/hold/exit`
  - strategist/scanner/monitor/commander summaries
  - outcome summary (`pnl`, `return_pct`, `holding_time`, `exit_reason`)
  - evidence completeness (`completeness_score`, `missing_sections`)
  - LLM summary status (`strategist_llm_status`, `brief_llm_status`, `ai_report_status`)
  - refs (`canonical_refs`, `llm_refs`, `artifact_links`)
- Bundle generation is resilient to missing sections and LLM failure.

### Storage / Duplication Policy
- Forward writes to deprecated trade intermediates are disabled:
  - `brief_input.json`, `brief_compact_input.json`
  - `ai_trade_report_compact_input.json`
  - legacy lifecycle mirror files
- Legacy artifacts remain read-only fallback and are still loadable when present.

### Backward Compatibility
- No historical migration or deletion was performed.
- Reader precedence remains fallback-capable:
  1. normalized trade artifacts
  2. canonical artifacts
  3. events fallback
- Health audit now recognizes mixed legacy/canonical brief LLM duplicates across multiple path variants.

### Operator Usage Guidance
- Primary file for end-to-end understanding: `reports/trades/<day>/<trade_id>/lifecycle_bundle.json`
- Human-facing summaries:
  - `reports/trades/<day>/<trade_id>/reports/operator_brief.md`
  - `reports/trades/<day>/<trade_id>/reports/ai_trade_report.md`
- Source-of-truth raw LLM bodies:
  - `reports/llm/<day>/<run_id>/<component>/`

## Phase 4 Addendum (Strategy Learning + Feedback Loop)

### What Changed
- Added lightweight deterministic performance modules:
  - `libs/performance/performance_aggregator.py`
  - `libs/performance/playbook_stats.py`
  - `libs/performance/strategy_memory.py`
- Added performance output layer under:
  - `reports/performance/<YYYY-MM-DD>/summary.json`
  - `reports/performance/<YYYY-MM-DD>/playbook_stats.json`
  - `reports/performance/<YYYY-MM-DD>/symbol_stats.json`
  - `reports/performance/<YYYY-MM-DD>/strategy_memory.json`
- Strategist now ingests advisory strategy memory hints (best/worst playbooks, recent failures/success patterns, regime bias) into LLM input context without forcing decisions.
- Strategy-memory integration is additive only:
  - no execution path changes
  - no order-flow behavior changes
  - no hard overrides to strategist decision contract

### Metric Definitions (Deterministic)
- `win_rate`: winning trades / total trades
- `avg_return`, `avg_win`, `avg_loss`: trade-level return aggregates (fallback to pnl proxy when return missing)
- `profit_factor`: gross gains / gross losses (loss denominator protected)
- `max_drawdown`: cumulative trade-level equity drawdown approximation
- Playbook stats:
  - `usage_count`, `win_rate`, `avg_return`, `recent_performance`, `drawdown`, `stability_score`

### Feedback Loop Design
- Lifecycle bundles remain the source dataset for performance aggregation.
- Strategy memory is generated from deterministic JSON stats, then passed to strategist as advisory context.
- Strategist prompt includes memory hints but retains autonomous frame output.

### Backward Compatibility
- No trade/execution/approval behavior was changed.
- Existing reports/trades layout and readers remain intact.
- Performance files are additive and non-blocking.

### Future Extension Ideas
- Replace heuristic `stability_score` with calibrated weighting per regime/playbook.
- Add rolling window snapshots (e.g., 7d/30d) and decay weighting.
- Add offline ML/RL candidates on top of deterministic feature tables without impacting live execution path.
