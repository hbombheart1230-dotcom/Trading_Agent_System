# 2026-05-18 Reporting Hotspot Refactor Phase 11-14

## Active Order

This document is the active numbering anchor for the large reporting hotspot refactor.

### Phase 11 - `trade_report_ai.py`

- Slice 1: prompt/message builder split
- Slice 2: deterministic fallback report builder split
- Slice 3: LLM call/router/result parse split
- Slice 4: summary generation adapter split

### Phase 12 - `trade_report_markdown_clean.py`

- Slice 1: truth/cost/PnL section split
- Slice 2: scanner/selection section split
- Slice 3: monitor/exit section split
- Slice 4: strategy/memory section split

### Phase 13 - `trade_story_pipeline.py`

- Slice 1: evidence hydration split
- Slice 2: scanner/monitor/execution human payload split
- Slice 3: timeline/warnings/story summary split

### Phase 14 - Runtime Policy Cleanup

- Slice 1: remaining stable policy/output assembly split in `commander_runtime.py` and `scanner_node.py`
- This phase is optional unless Phase 11-13 broad regression remains stable.

## Current Status

### Phase 11 Slice 1 - Trade Report AI Prompting Boundary

Changed files:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_ai_prompting.py`

Extracted responsibilities:

- concise trade report message construction
- compact prompt input projection
- repair prompt construction
- normal trade report message construction

Design intent:

- keep prompt/message policy outside the main `trade_report_ai.py` report builder
- preserve existing private helper names in `trade_report_ai.py` through thin wrappers
- keep LLM call/router/result parsing in `trade_report_ai.py` until Phase 11 Slice 3

Runtime policy:

- no live restart
- no live trading behavior change
- report prompt construction boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_prompting.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice1-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice1-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_ai.py`: 8786
- `libs/reporting/trade_report_ai_prompting.py`: 267

### Phase 11 Slice 2 - Trade Report AI Deterministic Merge Boundary

Changed files:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_ai_deterministic.py`

Extracted responsibilities:

- deterministic report public entry adapter
- deterministic failure report generation
- deterministic shared facts construction
- deterministic backward-compatible alias attachment
- deterministic monitor snapshot construction
- deterministic market context enrichment
- deterministic scanner reason enrichment
- deterministic fallback section seed extraction
- deterministic news/theme scanner choice detail bullets
- AI candidate narrative merge over deterministic fallback sections
- fallback section usage tracking
- backward-compatible candidate timeline merge

Remaining in `trade_report_ai.py` for the next deterministic slice:

- the large `_fallback_report` body

Design intent:

- split deterministic/merge entry points first without moving the high-dependency fallback body in the same edit
- preserve existing public/private helper names in `trade_report_ai.py`
- reduce risk before moving the larger deterministic fallback body

Runtime policy:

- no live restart
- no live trading behavior change
- report deterministic merge boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_deterministic.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice2-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice2-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice2-failure-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice2-failure-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice2-sharedfacts-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice2-sharedfacts-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice2-monitor-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice2-monitor-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice2-enrich-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice2-enrich-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice2-seeds-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice2-seeds-batch`
  - 20 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice2-news-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice2-news-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_ai.py`: 8527
- `libs/reporting/trade_report_ai_deterministic.py`: 540

### Phase 11 Slice 3 - Trade Report AI LLM Attempt Boundary

Changed files:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_ai_llm.py`

Extracted responsibilities:

- trade report LLM retry loop
- router call timing and exception attempt capture
- JSON full/partial/parse-error classification
- Korean repair retry trigger decision
- repair message handoff between attempts

Remaining in `trade_report_ai.py`:

- model/profile resolution
- disabled/local-debug/client-missing fallback branches
- deterministic merge/failure attachment
- LLM response artifact final assembly

Design intent:

- keep prompt construction, deterministic fallback, and LLM attempt execution as separate module boundaries
- preserve existing status strings and response artifact payloads
- avoid changing router policy, retry count, or token budget behavior

Runtime policy:

- no live restart
- no live trading behavior change
- report LLM call/parse boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_llm.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice3-llm-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice3-llm-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_ai.py`: 8363
- `libs/reporting/trade_report_ai_llm.py`: 240

### Phase 11 Slice 4 - Trade Summary Generation Adapter

Changed files:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_ai_summary_adapter.py`

Extracted responsibilities:

- trade summary evaluation schema constants
- trade summary evaluation output template
- trade summary evaluation normalization
- trade summary parse metadata
- trade summary LLM message construction
- deterministic trade summary report shell

Remaining in `trade_report_ai.py`:

- summary model/profile/runtime option resolution
- summary router availability checks
- summary LLM attempt loop and response artifact assembly
- markdown render adapters

Design intent:

- keep summary schema/message policy outside the main trade report AI file
- preserve existing private helper names through wrappers
- avoid changing summary LLM enablement, retry, timeout, or artifact behavior

Runtime policy:

- no live restart
- no live trading behavior change
- summary adapter/reporting boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_ai_summary_adapter.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase11-slice4-summary-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase11-slice4-summary-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_ai.py`: 8288
- `libs/reporting/trade_report_ai_summary_adapter.py`: 144

### Phase 11 Completion Snapshot

Phase 11 completed all planned slices.

New module boundaries:

- `libs/reporting/trade_report_ai_prompting.py`
- `libs/reporting/trade_report_ai_deterministic.py`
- `libs/reporting/trade_report_ai_llm.py`
- `libs/reporting/trade_report_ai_summary_adapter.py`

Current next phase:

- Phase 12 Slice 1 - `trade_report_markdown_clean.py` truth/cost/PnL section split

### Phase 12 Slice 1 - Markdown Truth/Cost/PnL Boundary

Changed files:

- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/trade_report_markdown_truth.py`

Extracted responsibilities:

- Truth Surface resolution fallback
- truth source label mapping
- PnL percentage display fallback handling
- broker/observed/net return cost analysis
- quantity extraction/inference from execution artifacts and cost facts
- cost analysis markdown bullet generation
- PnL basis label for ka10077 authoritative/matching status

Remaining in `trade_report_markdown_clean.py`:

- main Truth Surface section renderer
- summary markdown composition
- execution quality section copy that embeds truth facts
- monitor/exit/strategy/memory sections for later Phase 12 slices

Design intent:

- move immutable truth/cost math out of the large markdown renderer
- preserve existing private helper names through thin wrappers
- keep rendered markdown text identical while making the cost/PnL policy easier to audit

Runtime policy:

- no live restart
- no live trading behavior change
- markdown/trade summary rendering boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_markdown_clean.py libs\reporting\trade_report_markdown_truth.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase12-slice1-truth-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase12-slice1-truth-summary`
  - 6 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase12-slice1-truth-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_markdown_clean.py`: 6035
- `libs/reporting/trade_report_markdown_truth.py`: 307

Current next phase:

- Phase 12 Slice 2 - `trade_report_markdown_clean.py` scanner/selection section split

### Phase 12 Slice 2 - Markdown Scanner/Selection Boundary

Changed files:

- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/trade_report_markdown_scanner.py`

Extracted responsibilities:

- scanner/execution mismatch line detection
- scanner selection label filtering
- redundant symbol selection bullet filtering
- selected symbol section rendering
- scanner ranked-candidate comparison rendering
- top-pick blocked / runner-up re-evaluation wording
- stale scanner-symbol re-anchor guardrails

Remaining in `trade_report_markdown_clean.py`:

- wrappers that preserve existing private helper names
- shared formatting/translation helpers
- entry/guard/monitor/exit rendering for later slices

Design intent:

- keep scanner selection interpretation separate from the large markdown renderer
- preserve existing output copy by injecting formatter/translator callbacks
- make scanner/monitor mismatch handling easier to audit without touching execution logic

Runtime policy:

- no live restart
- no live trading behavior change
- markdown scanner/selection rendering boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_markdown_clean.py libs\reporting\trade_report_markdown_scanner.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase12-slice2-scanner-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase12-slice2-scanner-summary`
  - 6 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase12-slice2-scanner-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_markdown_clean.py`: 5803
- `libs/reporting/trade_report_markdown_scanner.py`: 326

Current next phase:

- Phase 12 Slice 3 - `trade_report_markdown_clean.py` monitor/exit section split

### Phase 12 Slice 3 - Markdown Monitor/Exit Boundary

Changed files:

- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/trade_report_markdown_monitor.py`

Extracted responsibilities:

- monitor bullet parsing
- closed-trade monitor wording normalization
- closed-trade monitor/truth preface rendering
- holding story section rendering
- exit decision section rendering
- monitor snapshot section rendering
- monitor price source and price source policy labels

Remaining in `trade_report_markdown_clean.py`:

- wrappers that preserve existing private helper names
- summary-input exit signal snapshot parser/enricher
- execution quality section
- strategy/memory rendering for Phase 12 Slice 4

Design intent:

- isolate monitor/exit human wording from the large markdown renderer
- keep Truth Surface vs monitor observation wording explicit
- avoid changing monitor policy, exit policy, or post-exit behavior

Runtime policy:

- no live restart
- no live trading behavior change
- markdown monitor/exit rendering boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_markdown_clean.py libs\reporting\trade_report_markdown_monitor.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase12-slice3-monitor-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase12-slice3-monitor-summary`
  - 6 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase12-slice3-monitor-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_markdown_clean.py`: 5682
- `libs/reporting/trade_report_markdown_monitor.py`: 294

Current next phase:

- Phase 12 Slice 4 - `trade_report_markdown_clean.py` strategy/memory section split

### Phase 12 Slice 4 - Markdown Strategy Horizon Boundary

Changed files:

- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/trade_report_markdown_strategy_memory.py`

Extracted responsibilities:

- strategy horizon label mapping
- strategy horizon reason/alignment labels
- compact duration and hold-window rendering
- strategy horizon report-surface hydration
- strategy horizon markdown section rendering

Deferred within strategy/memory area:

- full prompt-proven memory section rendering remains in `trade_report_markdown_clean.py`
- full reconstructed memory section rendering remains in `trade_report_markdown_clean.py`
- full deterministic memory application section rendering remains in `trade_report_markdown_clean.py`
- market/strategist output detail rendering remains in `trade_report_markdown_clean.py`

Reason for deferral:

- those sections share many reporter, market, strategy-output, and memory-label callbacks
- moving them as one block would produce a very large callback boundary
- the current slice still extracts the highest-risk strategy-horizon behavior surface and keeps the output stable

Runtime policy:

- no live restart
- no live trading behavior change
- strategy horizon markdown/reporting boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_markdown_clean.py libs\reporting\trade_report_markdown_strategy_memory.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py -q --basetemp .pytest-work-phase12-slice4-strategy-ai`
  - 128 passed
- `venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_korea_market_indices_context.py -q --basetemp .pytest-work-phase12-slice4-strategy-summary`
  - 6 passed
- `venv\Scripts\python.exe -m pytest tests\test_run_ai_trade_report_batch.py tests\test_trade_report_ai_separated_adapter.py -q --basetemp .pytest-work-phase12-slice4-strategy-batch`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_report_markdown_clean.py`: 5454
- `libs/reporting/trade_report_markdown_strategy_memory.py`: 319

### Phase 12 Completion Snapshot

Phase 12 completed all planned slices at the reporting boundary level.

New module boundaries:

- `libs/reporting/trade_report_markdown_truth.py`
- `libs/reporting/trade_report_markdown_scanner.py`
- `libs/reporting/trade_report_markdown_monitor.py`
- `libs/reporting/trade_report_markdown_strategy_memory.py`

Current next phase:

- Phase 13 Slice 1 - `trade_story_pipeline.py` evidence hydration split

### Phase 13 Slice 1 - Trade Story Evidence Hydration Boundary

Changed files:

- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_story_pipeline_evidence_hydration.py`

Extracted responsibilities:

- safe JSON artifact loading
- canonical agent artifact hydration from artifact paths
- scanner sibling `monitor.json` selection for monitor-fallback reanchor evidence
- fallback to in-bundle monitor artifact when sibling monitor evidence is unavailable

Remaining in `trade_story_pipeline.py`:

- scanner/monitor/execution human payload assembly
- strategist evidence trace construction
- lifecycle/timeline/warning/story summary assembly

Design intent:

- isolate file-system artifact hydration from story model assembly
- preserve existing private helper names through wrappers
- keep monitor fallback reanchor behavior unchanged

Runtime policy:

- no live restart
- no live trading behavior change
- story evidence hydration boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_story_pipeline.py libs\reporting\trade_story_pipeline_evidence_hydration.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py -q --basetemp .pytest-work-phase13-slice1-story`
  - 35 passed
- `venv\Scripts\python.exe -m pytest tests\test_phase3_lifecycle_bundle.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase13-slice1-provenance`
  - 9 passed
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase13-slice1-livebundle`
  - 67 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_story_pipeline.py`: 4703
- `libs/reporting/trade_story_pipeline_evidence_hydration.py`: 82

Current next phase:

- Phase 13 Slice 2 - scanner/monitor/execution human payload split

### Phase 13 Slice 2 - Trade Story Monitor/Execution Human Payload Boundary

Changed files:

- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_story_pipeline_human_payloads.py`

Extracted responsibilities:

- monitor stop-policy trace assembly
- strategist adaptive exit / adaptive stop lookup used by monitor payloads
- monitor entry blocker trace assembly
- execution outcome human payload adapter

Remaining in `trade_story_pipeline.py`:

- full scanner reason enrichment and selection payload assembly
- full monitor reason narrative body
- filters human payload assembly
- timeline/warnings/story summary assembly

Reason for keeping scanner body in place this slice:

- scanner reason generation still shares many score, theme, news, selection, and fallback helpers
- moving the whole function now would create a large callback-heavy boundary
- this slice moves the monitor/execution policy payloads first, which are more stable and easier to extend independently

Design intent:

- keep existing private helper names through wrappers
- move monitor policy payload logic into a file that can grow without touching the story pipeline core
- preserve execution outcome behavior by delegating to the same underlying text payload builder

Runtime policy:

- no live restart
- no live trading behavior change
- story reporting payload boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_story_pipeline.py libs\reporting\trade_story_pipeline_human_payloads.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py -q --basetemp .pytest-work-phase13-slice2-human`
  - 35 passed
- `venv\Scripts\python.exe -m pytest tests\test_phase3_lifecycle_bundle.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase13-slice2-provenance`
  - 9 passed
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase13-slice2-livebundle`
  - 67 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_story_pipeline.py`: 4607
- `libs/reporting/trade_story_pipeline_human_payloads.py`: 149

Current next phase:

- Phase 13 Slice 3 - timeline/warnings/story summary split

### Phase 13 Slice 3 - Trade Story Timeline/Warnings/Lifecycle Assembly Boundary

Changed files:

- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_story_pipeline_story_assembly.py`

Extracted responsibilities:

- timeline row construction
- story warning collection and dedupe
- lifecycle input normalization for story generation
- compact canonical monitor snapshot construction

Remaining in `trade_story_pipeline.py`:

- main `build_trade_story_input` orchestration
- scanner reason enrichment and selection reanchor
- monitor reason narrative body
- reasoning trace/provenance assembly
- final story dictionary composition

Reason for boundary shape:

- `build_trade_story_input` is still a large orchestration function with many cross-section dependencies
- moving it wholesale would make a broad, risky callback boundary
- this slice removes the standalone story assembly helpers first and keeps the public helper names stable through wrappers

Design intent:

- isolate low-level story assembly helpers from core orchestration
- keep lifecycle normalization extensible without touching the full story pipeline
- preserve existing story input schema and output keys

Runtime policy:

- no live restart
- no live trading behavior change
- story reporting assembly boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_story_pipeline.py libs\reporting\trade_story_pipeline_story_assembly.py`
- `venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py -q --basetemp .pytest-work-phase13-slice3-story`
  - 35 passed
- `venv\Scripts\python.exe -m pytest tests\test_phase3_lifecycle_bundle.py tests\test_reporting_provenance_preference.py -q --basetemp .pytest-work-phase13-slice3-provenance`
  - 9 passed
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q --basetemp .pytest-work-phase13-slice3-livebundle`
  - 67 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after slice:

- `libs/reporting/trade_story_pipeline.py`: 4490
- `libs/reporting/trade_story_pipeline_story_assembly.py`: 186

Current next phase:

- Phase 13 completion review, then Phase 14 optional stability/output assembly split

### Phase 14 - Commander/Scanner Output Assembly Boundary

Changed files:

- `graphs/commander_runtime.py`
- `graphs/nodes/scanner_node.py`
- `libs/runtime/commander/output_frames.py`
- `libs/runtime/scanner/output_payloads.py`

Extracted responsibilities:

- commander decision frame output assembly
- scanner candidate ranking table payload assembly
- scanner candidate selection reason payload assembly

Remaining in original runtime files:

- commander route/path execution
- commander resilience/cooldown/fast-path decisions
- scanner candidate pool construction
- scanner scoring, ranking, practical filters, market representative guard, and state mutation

Boundary rationale:

- this phase touches live runtime-adjacent files, so logic movement was limited to deterministic output payload builders
- policy decisions and execution paths remain in place
- public state keys are unchanged: `commander_decision_frame`, `scanner_candidate_ranking_table`, `scanner_candidate_selection_reason`

Runtime policy:

- no live restart
- no live trading behavior change
- output assembly boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile graphs\commander_runtime.py graphs\nodes\scanner_node.py libs\runtime\commander\output_frames.py libs\runtime\scanner\output_payloads.py`
- `venv\Scripts\python.exe -m pytest tests\test_m21_commander_runtime_entry.py -q --basetemp .pytest-work-phase14-commander`
  - 81 passed
- `venv\Scripts\python.exe -m pytest tests\test_scanner_strategy_frame_integration.py tests\test_scanner_monitor_compatibility.py -q --basetemp .pytest-work-phase14-scanner`
  - 24 passed
- `venv\Scripts\python.exe -m pytest tests\test_scanner_policy_overlay.py tests\test_scanner_memory_bias.py tests\test_m23_4_commander_incident_cooldown_routing.py -q --basetemp .pytest-work-phase14-policy`
  - 20 passed
- `git diff --check`
  - passed with CRLF warnings only

Line counts after phase:

- `graphs/commander_runtime.py`: 5783
- `graphs/nodes/scanner_node.py`: 4030
- `libs/runtime/commander/output_frames.py`: 55
- `libs/runtime/scanner/output_payloads.py`: 141

Current next phase:

- Phase 14 completion review and broad regression candidate selection
