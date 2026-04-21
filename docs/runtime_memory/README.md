# Runtime Memory Docs

## Goal

This folder defines how runtime memory should be structured and reused across the trading system.

These documents are not limited to trade-report generation.
They cover the memory surfaces that should shape:

- the first strategist pass
- scanner deterministic ranking adjustments
- selected-symbol or long-hold strategist refresh
- future report pruning decisions

## Scope Split

Use `docs/trade_report_plan` for:

- trade report runtime ownership
- report generation guardrails
- report surface pruning
- reporter lane ownership

Use `docs/runtime_memory` for:

- market memory
- symbol memory
- position refresh memory
- retrospective strategist feedback adapters
- future usage matrices and memory flow contracts

## Current Contracts

1. `market_memory_contract_2026-04-19.md`
- pre-selection strategist memory
- current canonical surface:
  - `reports/performance/<day>/strategy_memory.json`
- future weekly / monthly / aggregate extensions can remain under `reports/performance/*`

2. `symbol_memory_contract_2026-04-19.md`
- scanner deterministic symbol priors
- selected-symbol refresh memory
- current canonical surface:
  - `reports/symbols/<SYMBOL>/symbol_memory.json`

3. `position_refresh_contract_2026-04-19.md`
- long-hold / repeated-hold strategist refresh packet

4. `reports_usage_matrix_2026-04-19.md`
- classifies `reports/*` by runtime role, memory value, and pruning status

5. `strategist_memory_packet_visibility_2026-04-20.md`
- explains where report-derived packets are actually visible in strategist artifacts
- distinguishes:
  - full prompt-payload proof
  - normalized canonical strategist proof
  - empty vs populated `selected_symbol_memory`
- records the current observability gap where some commander refresh runs do not persist matching strategist prompt/canonical artifacts

## Existing Adapter Layer

Not every related module is a primary runtime-memory owner.

Current existing adapter of note:

- `libs/reporting/strategy_read_model.py`
  - not broad market memory
  - not symbol-memory canonical storage
  - instead, a retrospective strategist-feedback adapter built from trade-story artifacts
  - used for:
    - trade-story linkage views
    - compact strategist feedback inputs
    - recent strategist feedback windows

## Trade-Level Canonical Surface

`libs/reporting/trade_read_model.py` is now the canonical per-trade read-model owner for:

- deterministic trade facts
- provenance and canonical artifact paths
- normalized runtime context
- normalized report section seeds

`libs/reporting/trade_story_pipeline.py` is the current story-input producer that writes the matching section-seed payloads into trade-story inputs:

- `report_section_seeds`
- `section_provenance.report_section_provenance_seeds`

`libs/reporting/reasoning_trace.py` should treat those same section seeds as canonical fallback summaries before falling back to raw `*_human` blocks.

Current status:

- the `trade_story_pipeline.py -> trade_read_model.py -> trade_report_ai.py` section-seed chain is now aligned at the producer / owner / consumer level
- `trade_report_ai.py` broad regression coverage (`tests/test_trade_report_ai.py`, `tests/test_trade_report_ai_separated_adapter.py`) is currently green after the latest canonicalization pass
- remaining trade-report work should prefer incremental pruning around this canonical chain rather than new sibling adapters

The current section-seed surface exposed through `trade_read_model.context.report_section_seeds` includes:

- `market_context_at_entry`
- `strategist_summary`
- `why_this_symbol_was_chosen`
- `entry_decision`
- `holding_monitoring_story`
- `exit_decision`
- `scanner_filters`
- `execution_quality`
- `guard_approval_result`
- `reporter_evaluation`
- `final_operator_conclusion`

Consumers should prefer this surface over re-normalizing raw:

- `market_context_human`
- `scanner_reason_human`
- `filters_human`
- downstream strategist / entry sections that can be derived from those same normalized inputs

## Current Implementation Direction

The current implementation direction is:

1. strategist pass 1
- read broad market memory from `reports/performance/<day>/strategy_memory.json`

2. scanner deterministic ranking
- read symbol priors from `reports/symbols/<SYMBOL>/symbol_memory.json`
- do not add a scanner LLM

3. monitor execution
- execute inherited policy and deterministic scanner outputs

4. strategist pass 2 refresh
- allowed only after symbol selection or during long-hold / repeated-hold reframe
- consume position-refresh packet and selected-symbol memory excerpt
- do not re-run scanner

5. trade-report adapter
- `libs/reporting/trade_report_ai.py` should consume `trade_read_model` facts/context/section seeds
- section-level provenance should prefer section-seed provenance over legacy raw `*_human` provenance
