# Report Agentization Plan

## Purpose
We are evolving the current deterministic report pipeline into a Reporter-owned service layer.

Immediate goals:
- keep existing `libs/reporting/*` logic intact
- make `libs/agent/reporter.py` the orchestration entrypoint for report generation
- preserve canonical artifact, route provenance, freshness/stale metadata, and narrative axis behavior
- keep runtime trading semantics unchanged

## Current baseline
Already aligned:
- canonical artifact as the primary source of truth
- route provenance aligned around commander canonical artifacts
- freshness and stale metadata added to operator-facing reports
- entry and exit narrative axes separated in report rendering
- daily/operator report cross-dependency reduced

Current structure:
- report rendering still lives in `libs/reporting/*`
- several CLI scripts still call reporting functions directly
- Reporter exists, but until this phase it was mostly passive (`build`, `analyze_event_logs`)

## Problem statement
The repo has strong reporting logic, but ownership is fragmented.
That makes it harder to:
- treat reporting as an agent/service boundary
- move scripts toward thin wrappers later
- attach future Reporter input/output contracts without rewriting existing generators

## Phase 1 objective
Phase 1 is intentionally narrow.
We will:
- promote `libs/agent/reporter.py` into a Reporter orchestration service
- add public methods for the current report surfaces
- reuse existing generators instead of moving rendering logic
- keep output semantics and file layout unchanged

We will not:
- change runtime trading semantics
- change Monitor / Supervisor / Executor / Guard behavior
- rewrite reporting business logic
- move report generation fully out of scripts in one step

## Reporter service boundary
Reporter owns orchestration only.

Reporter responsibilities:
- normalize report inputs such as `day`, `report_dir`, and report-specific options
- dispatch to the existing canonical generators
- return stable payload + path metadata to callers

Existing reporting modules remain responsible for:
- aggregation rules
- route provenance logic
- freshness/stale logic
- markdown/json rendering
- path policy such as the official `trade_explain` output path

## Public service API baseline
Phase 1 Reporter service should expose these entrypoints:
- `generate_daily_report(...)`
- `generate_operator_summary(...)`
- `generate_trade_explain(...)`
- `generate_metrics_report(...)`
- `generate_run_cards(...)`
- `generate_decision_story(...)`
- `analyze_event_logs(...)`
- optional dispatch helper: `run(mode=..., ...)`

## Output and semantics policy
Reporter orchestration must preserve:
- canonical artifact usage
- route source / route provenance policy
- freshness / stale metadata
- narrative axis rules
- official report path policy

Runtime semantics unchanged:
- Monitor must never place orders
- execution semantics do not change
- approval / risk / guard precedence do not change
- logging remains observational only

## Phase 1 success criteria
We consider Phase 1 complete when:
- Reporter can generate all current operator-facing report surfaces through a service API
- existing scripts can start delegating to Reporter without changing report meaning
- continuity tests still pass
- source/provenance/freshness metadata remain intact

## Next steps
Phase 2:
- formal Reporter input/output contracts
- make more scripts thin wrappers around Reporter service methods

Phase 3:
- optional LLM insight layer on top of deterministic report outputs

Phase 4:
- Commander and Strategist consume Reporter output through explicit contracts
