# Reports Usage Matrix (2026-04-19)

## Goal

This document classifies each top-level `reports/*` surface by actual runtime role.

The classification is not based on folder names alone.
It is based on:

- runtime ownership
- current code consumers
- operator value
- strategist/scanner/refresh memory value

## Classification Labels

- `runtime_source`
  - source-of-truth runtime artifacts
- `operator_surface`
  - reports operators should read directly
- `market_memory_source`
  - source material for strategist pre-selection memory
- `symbol_memory_source`
  - source material for scanner deterministic symbol priors and selected-symbol refresh
- `position_refresh_source`
  - source material for long-hold strategist refresh
- `debug_only`
  - repair, replay, diagnostics, or audit
- `legacy_fallback`
  - compatibility output that should not define future design
- `prune_now`
  - low-value surface that should not remain a default generated report

## Top-Level Matrix

| Path | Primary Role | Current Value | Primary Consumers | Decision |
|---|---|---|---|---|
| `reports/canonical` | `runtime_source` | essential | strategist, scanner, monitor, executor, trade-report runtime | keep |
| `reports/trades` | `operator_surface` | essential | operator, trade report readers | keep |
| `reports/daily` | `operator_surface`, `market_memory_source` | high | operator, future strategist memory builder | keep |
| `reports/metrics` | `operator_surface`, `market_memory_source`, `symbol_memory_source` | high | operator, future strategist/scanner memory builder | keep |
| `reports/symbols` | currently weak operator surface, should become `symbol_memory_source` | medium | future scanner/selected-symbol refresh | keep but redefine |
| `reports/live_summary` | operator telemetry | medium | session operator | keep |
| `reports/live_watch` | operator telemetry | medium | session operator | keep |
| `reports/llm` | `debug_only` | high for audit, low for operator | prompt/response audit | keep hidden |
| `reports/runtime` | `debug_only` | high for runtime control | locks, queues, runtime state | keep hidden |
| `reports/dev` | `debug_only` | mixed | diagnostics, replay, analysis | keep hidden |
| `reports/operator_summary` | `legacy_fallback` | low | deprecated residue only | moved to `_legacy_backup`; do not recreate |
| `reports/trade_explain` | `legacy_fallback` | low | deprecated residue only | moved to `_legacy_backup`; canonical surface is `reports/dev/analysis/trade_explain` |
| `reports/decision_story` | low-value operator surface | low | deprecated residue only | moved to `_legacy_backup`; manual default moved under `reports/dev/manual/decision_story` |
| `reports/run_cards` | low-value operator surface | low | deprecated residue only | moved to `_legacy_backup`; manual default moved under `reports/dev/manual/run_cards` |
| `reports/milestones` | governance / validation | medium | readiness / quality gates | keep outside memory surfaces |

## `reports/dev` Subclassification

| Path | Role | Consumers | Decision |
|---|---|---|---|
| `reports/dev/analysis/reporter_analysis` | `market_memory_source` candidate | strategist feedback packet, diagnostics | keep and reinterpret |
| `reports/dev/analysis/live_execution_bundles` | `debug_only`, trade-report repair source | trade-report runtime, replay | keep hidden |
| `reports/dev/analysis/trade_explain` | `debug_only`, reporter-analysis source | reporter feedback, manual reading | keep as canonical `trade_explain` surface |
| `reports/dev/live/*` | legacy telemetry fallback | old live visibility paths | retire after confirming root `live_*` consumers |
| `reports/dev/catalog/*` | debug/report inventory | maintenance only | keep hidden |
| `reports/dev/exam/*` | mock exam diagnostics | test/ops only | keep hidden |

## Memory Mapping

### Market Memory Source

Primary upstream sources:

- `reports/daily`
- `reports/metrics`
- `reports/dev/analysis/reporter_analysis`
- deterministic trade read model
- `reports/canonical`

Current canonical packet:

- `reports/performance/<day>/strategy_memory.json`

These should feed:

- `docs/runtime_memory/market_memory_contract_2026-04-19.md`

### Symbol Memory Source

Primary upstream sources:

- `reports/symbols` after redesign
- `reports/trades`
- `reports/metrics`
- deterministic trade read model
- execution evidence from `reports/canonical`

Current canonical packet:

- `reports/symbols/<SYMBOL>/symbol_memory.json`

These should feed:

- `docs/runtime_memory/symbol_memory_contract_2026-04-19.md`

### Position Refresh Source

Primary upstream sources:

- open-position runtime state
- `reports/canonical` monitor / commander / executor artifacts
- symbol memory packet
- selected-trade evidence from `reports/trades`

These should feed:

- `docs/runtime_memory/position_refresh_contract_2026-04-19.md`

## Existing Read-Model / Adapter Split

These are related but do not own the same memory layer:

| Module | Primary Role | Decision |
|---|---|---|
| `libs/performance/strategy_memory.py` | canonical broad market-memory packet builder | keep as market-memory owner |
| `libs/reporting/symbol_read_model.py` | compatibility reader for symbol memory and historical fallback | keep, gradually thin to adapter |
| `libs/reporting/strategy_read_model.py` | retrospective strategist-feedback adapter from trade-story artifacts | keep, do not merge into market memory |
| `libs/reporting/trade_read_model.py` | canonical per-trade read model / fact surface | keep as trade-level read-model owner |

## Owner / Adapter / Fallback Map

This table is the practical cleanup guide for nearby modules.

| Module | Classification | Runtime Role | Current Consumers | Direction |
|---|---|---|---|---|
| `libs/performance/strategy_memory.py` | `owner` | broad pre-selection strategist memory | strategist 1st pass | keep and extend |
| `libs/reporting/symbol_trade_report.py` | `owner` | persisted symbol-memory source material and `symbol_memory.json` writer | symbol history generation | keep and simplify around `symbol_memory.json` |
| `libs/reporting/symbol_read_model.py` | `adapter` | reads persisted symbol memory and falls back to historical aggregation | scanner, strategist symbol priors, operator visibility | keep, thin over time |
| `libs/reporting/strategy_read_model.py` | `adapter` | builds retrospective strategist feedback packets from trade-story artifacts | trade-story pipeline, trade read model, agent pipeline trace | keep, do not confuse with market memory |
| `libs/reporting/trade_read_model.py` | `owner` | canonical per-trade read model / fact surface and normalized report-section seeds | strategist deterministic facts, reporter agent, trade-report adapters, symbol read model | keep as core trade-level owner |
| `libs/reporting/trade_story_pipeline.py` | `producer` | writes trade-story inputs and canonical report-section seed payloads | live bundle runner, fallback generators, trade read model readers | keep as producer; avoid duplicate seed shaping |
| `libs/reporting/single_trade_report.py` | `fallback` | manual one-shot trade-report generator | manual tests / compatibility paths only | keep degraded, do not restore as live default |

### Guardrails

1. Do not move `trade_read_model.py` logic into UI or report markdown adapters.
2. Do not promote `single_trade_report.py` back into live intraday ownership.
3. Do not merge `strategy_read_model.py` into `strategy_memory.py`; they serve different horizons.
4. Prefer shrinking adapters around canonical owners rather than introducing new sibling modules.

### Current Trade-Report Consumer Direction

- `libs/reporting/trade_report_ai.py`
  - should consume:
    - `trade_read_model.facts`
    - `trade_read_model.context`
    - `trade_read_model.context.report_section_seeds`
  - should not re-normalize raw `market_context_human` / `scanner_reason_human` / `filters_human` when the canonical trade-read-model surface is available
  - current section-seed scope:
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

- `libs/reporting/trade_story_pipeline.py`
  - should write:
    - `report_section_seeds`
    - `section_provenance.report_section_provenance_seeds`
  - should remain the story-input producer while `trade_read_model.py` remains the canonical read surface

- section provenance inside `trade_report_ai.py`
  - should prefer section-specific provenance and section-seed provenance
  - legacy raw `*_human` provenance should remain fallback only

## Immediate Pruning Decisions

These should not remain part of the default reporting surface:

- `reports/decision_story`
- `reports/run_cards`

Current status:
- default generation via `reporter_analysis` is disabled
- live trade-report lane no longer reads legacy top-level `operator_summary`
- `daily_artifact_paths()` no longer exposes legacy top-level `operator_summary` paths
- report maintenance now inspects canonical daily `operator_summary` only
- operator UI overview/data access now reads canonical daily `operator_summary` only
- `Reporter.generate_operator_summary(...)` no longer treats `operator_summary`-named custom roots as canonical
- `Reporter.generate_decision_story(...)` and `Reporter.generate_run_cards(...)` no longer treat old surface names as canonical roots
- deprecated top-level `reports/operator_summary`, `reports/trade_explain`, `reports/decision_story`, and `reports/run_cards` were moved to `reports/_legacy_backup/report_surface_cleanup_2026-04-19`
- manual defaults for `decision_story` / `run_cards` now write under `reports/dev/manual/*`
- `reporter_analysis` and `operator_visibility` internal generation paths for `decision_story` / `run_cards` now also write under `reports/dev/manual/*`
- closeout opt-in generation in `run_mock_exam_day.py` now writes `decision_story` / `run_cards` under `reports/dev/manual/*`
- phase5 validation bundle generation also writes `decision_story` / `run_cards` under `reports/dev/manual/*`
- report maintenance inventory and empty-report warnings now inspect `reports/dev/manual/*` instead of top-level `reports/decision_story` / `reports/run_cards`
- strategist feedback packet no longer auto-loads stored `trade_explain` day files
- `reporter_analysis` now generates `trade_explain` only under `reports/dev/analysis/trade_explain`
- manual generation paths remain available

These should not define future memory contracts:

- top-level `reports/trade_explain`
- top-level `reports/operator_summary`

## Redefine Instead Of Delete

### `reports/symbols`

Do not delete.

Redefine it as:

- canonical `symbol_memory_source`
- home of `reports/symbols/<SYMBOL>/symbol_memory.json`
- scanner deterministic symbol prior input
- selected-symbol refresh memory input

### `reports/dev/analysis/reporter_analysis`

Do not treat it as a daily operator-facing end product.

Treat it as:

- compressed diagnosis source
- upstream input for strategist-facing market memory packets

## Design Rule

From this point forward, a report should survive only if it satisfies at least one of these:

1. it is a runtime source-of-truth
2. it is an operator-critical surface
3. it is a memory source for strategist/scanner/position refresh
4. it is necessary for debug, replay, or audit

If a report satisfies none of those, it should not remain a default generated artifact.
