# Incremental Refactor Plan - 2026-05-15

## Purpose

This plan defines how to improve the Trading Agent System without a large, risky rewrite.

The current system already has broad runtime coverage, canonical artifacts, operator reports, and a large regression test set. The main risk is not missing features. The main risk is that recent live patches have accumulated inside a few large hot-path files, making behavior harder to audit and harder to extend safely.

The refactor must therefore be incremental, behavior-preserving by default, and guarded by targeted tests at every step.

## Current Baseline

- Python source inspected across `libs`, `graphs`, `scripts`, and `apps`.
- Test collection baseline: `1979 tests collected`.
- Existing focused smoke:
  - `tests/test_runtime_entrypoint_import_boundaries.py`
  - commander env migration doc tests
- Largest ownership hotspots:
  - `graphs/nodes/monitor_node.py`
  - `graphs/nodes/strategist_node.py`
  - `graphs/nodes/scanner_node.py`
  - `graphs/commander_runtime.py`
  - `graphs/nodes/execute_from_packet.py`
  - `libs/reporting/trade_report_ai.py`
  - `libs/reporting/trade_report_markdown_clean.py`
  - `libs/reporting/trade_story_pipeline.py`
  - `apps/operator_ui/data_access_core.py`

## Non-Negotiable Rules

1. Do not do one large cross-system rewrite.
2. Do not change trading behavior while extracting code unless the step explicitly says it is a behavior patch.
3. Keep every extraction small enough to validate with focused tests.
4. Keep live-operational patches and structural refactors separate.
5. Preserve existing public state keys and canonical artifact fields unless a migration step explicitly introduces aliases.
6. Do not remove fallback behavior until the replacement path has runtime evidence and tests.
7. Prefer new narrow modules over adding more helper functions to large modules.
8. Scripts remain process boundaries. Reusable logic belongs under `libs/*`.
9. Report rendering must not compute truth values. Truth values must come from a resolver/read model.
10. Every phase must have a rollback criterion.

## Workstream Overview

The refactor is split into four workstreams:

- Monitor and exit logic
- Executor order lifecycle
- Reporter truth and report rendering
- Configuration, contracts, and documentation hygiene

The recommended order is Monitor first, then Executor, then Reporter truth, then broad cleanup.

## Phase 0 - Safety Rails and Baseline

### Goal

Create a stable baseline before moving code.

### Scope

- Define focused test bundles for each hot path.
- Record current source-of-truth boundaries.
- Identify files that may be touched during each phase.
- Keep live behavior unchanged.

### Test Bundles

Monitor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_intraday_monitor_signals.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Executor bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_execute_from_packet.py tests\test_update_state_after_execution.py tests\test_order_client.py tests\test_real_executor_mock_mode_allowed.py tests\test_real_executor_disabled.py -q
```

Reporter truth bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_trade_story_pipeline_enrichment.py tests\test_run_ai_trade_report_batch.py -q
```

Runtime boundary bundle:

```text
venv\Scripts\python.exe -m pytest tests\test_runtime_entrypoint_import_boundaries.py tests\test_run_session.py tests\test_run_m13_live_loop_lock.py tests\test_live_loop_runner.py -q
```

Minimum syntax check:

```text
venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py graphs\nodes\execute_from_packet.py libs\runtime\exit_policy.py
```

### Completion Criteria

- Test bundle commands are documented.
- First refactor target has an explicit behavior snapshot.
- No runtime code is changed in this phase unless needed to preserve already patched behavior.

## Phase 1 - Monitor Exit Boundary

### Why First

Monitor exit logic is the most active live-patch area. Recent changes include:

- VWAP breakdown fresh-minute source preference
- VWAP breakdown confirmation
- peak drawdown profit protection
- time-limit reassessment
- cost-aware exit floor
- pending exit confirmation guards

This area is high value because bugs directly become premature sells or missed exits.

### Target Ownership

Current owner:

- `graphs/nodes/monitor_node.py`
- `libs/runtime/exit_policy.py`

Target modules:

- `libs/runtime/monitor_exit_inputs.py`
  - build the normalized exit policy map from state, selected row, position, features, and applied policy
- `libs/runtime/monitor_exit_confirmation.py`
  - confirmation counters, VWAP consecutive-bar confirmation, pending-exit metadata
- `libs/runtime/monitor_exit_observability.py`
  - monitor_exit payload shaping
- `libs/runtime/exit_policy.py`
  - pure policy evaluation only

### Step 1.1 - Extract VWAP Confirmation Helper

Move the VWAP breakdown confirmation helper out of `monitor_node.py` into a narrow runtime module.

Behavior must remain identical:

- hard stop and stop-loss remain immediate
- VWAP-only breakdown requires confirmation
- confirmation is satisfied by:
  - required consecutive bars
  - low breakdown
  - volume confirmation

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py::test_monitor_vwap_breakdown_exit_after_two_minute_confirmations tests\test_monitor_exit_guard.py::test_monitor_vwap_breakdown_exit_uses_feature_signal tests\test_strategy_sizing_exit_upgrade.py -q
```

Rollback criterion:

- Any change in SELL intent count or `monitor_exit.reason` outside the targeted VWAP tests.

### Step 1.2 - Extract Exit Input Builder

Move exit policy map assembly out of `monitor_node.py`.

No behavior change allowed. The function should accept explicit inputs and return a dict compatible with `evaluate_exit_policy`.

Required preserved fields:

- price and price source
- avg price and qty
- peak price
- hold seconds
- VWAP distance and source
- trend/volume/low-break metrics
- applied policy source
- cost-floor fields
- confirmation fields

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_strategy_sizing_exit_upgrade.py -q
```

Rollback criterion:

- Any regression in existing exit reason, hold block reason, or intent emission.

### Step 1.3 - Extract Exit Observability Builder

Move shaping of `state["monitor_exit"]` into a small builder.

No trading behavior change allowed.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py::test_monitor_reason_human_marks_pending_exit_as_mismatch_not_trigger tests\test_monitor_exit_guard.py -q
```

Rollback criterion:

- Reports or story pipeline lose fields needed to explain pending exits.

## Phase 2 - Monitor Entry Boundary

### Goal

Separate entry readiness from exit handling.

Current risks:

- human-chart score
- cost-adjusted edge
- candidate cascade
- closeout window
- post-exit cooldown
- open-position capacity

are all close together in `monitor_node.py`.

Target modules:

- `libs/runtime/monitor_entry_inputs.py`
- `libs/runtime/monitor_entry_quality.py`
- `libs/runtime/monitor_candidate_cascade.py` already exists and should be reused/expanded only if needed
- `libs/runtime/monitor_entry_observability.py`

### Step 2.1 - Entry Quality Extraction

Extract pure chart/quality scoring and preserve output field names.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_intraday_monitor_signals.py tests\test_chart_structure_features.py tests\test_monitor_exit_guard.py -q
```

### Step 2.2 - Entry Blocker Surface Extraction

Keep no-trade reason shaping outside core intent generation.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_decision_observability.py tests\test_entry_blocker_read_model.py tests\test_trade_story_pipeline_enrichment.py -q
```

## Phase 3 - Executor Order Lifecycle Boundary

### Why

Live trading risk is concentrated around pending orders, replacement orders, partial fills, and stale local state.

Current owner:

- `graphs/nodes/execute_from_packet.py`
- `graphs/nodes/update_state_after_execution.py`

Target modules:

- `libs/execution/order_lifecycle_policy.py`
  - pending buy cancel policy
  - pending sell replacement policy
  - market replacement eligibility
  - time-in-force handling
- `libs/execution/recent_order_guard.py`
  - recent buy guard
  - recent sell guard
  - partial-fill reflection guard
- `libs/execution/execution_truth_merge.py`
  - local order result plus broker response normalization

### Step 3.1 - Pending Order Policy Extraction

Move policy decisions only. Keep actual broker calls in current executor until the policy is stable.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_execute_from_packet.py::test_execute_from_packet_replaces_unfilled_sell_with_market_order tests\test_execute_from_packet.py::test_execute_from_packet_cancels_pending_unfilled_buy_without_market_replacement tests\test_execute_from_packet.py -q
```

### Step 3.2 - Recent Order Guard Extraction

Extract JSON state load/save and eligibility checks.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_execute_from_packet.py tests\test_update_state_after_execution.py -q
```

Rollback criterion:

- Any duplicate buy/sell protection weakens.
- Any emergency sell is blocked unexpectedly.

## Phase 4 - Reporter Truth Boundary

### Why

The report system is currently the hardest place to reason about truth because it combines:

- broker truth
- local lifecycle
- fallback mark-to-market estimates
- LLM output
- markdown wording
- operator summary

The MTS/API return mismatch work should not live in markdown rendering.

Target modules:

- `libs/reporting/trade_truth_resolver.py`
  - canonical truth precedence
  - broker realized PnL pct
  - local estimate
  - fallback mark-only result
  - confidence/authority label
- `libs/reporting/trade_fill_aggregator.py`
  - partial buy/sell fill aggregation
  - per-order and per-trade grouping
- `libs/reporting/trade_summary_renderer.py`
  - summary markdown only

### Step 4.1 - Truth Resolver Scaffold

Create resolver around existing behavior with no output change.

Inputs:

- lifecycle bundle
- broker day truth
- execution snapshots
- report shared facts

Outputs:

- authoritative_pct
- authoritative_pnl_krw
- pct_basis
- authority
- fallback_pct
- fallback_role
- confidence
- warnings

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py tests\test_trade_summary_symbol_metadata.py tests\test_broker_cost_profile.py tests\test_kiwoom_day_trade_truth.py -q
```

Rollback criterion:

- Any report changes realized PnL label or authoritative/fallback role unexpectedly.

### Step 4.2 - Fill Aggregation

Separate split-fill grouping from report text.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_broker_trade_reconciliation.py tests\test_update_state_after_execution.py tests\test_trade_report_ai.py -q
```

## Phase 5 - Strategist and Scanner Policy Surface

### Goal

Reduce env/direct-dict drift and make playbook expansion manageable.

Current issues:

- many direct env reads in `strategist_node.py` and `scanner_node.py`
- playbook/subtype strings spread across strategist, scanner, monitor, reports
- strategy registry exists but is not the center of runtime strategy behavior

Target modules:

- `libs/strategies/registry.py`
- `libs/strategies/playbook_contracts.py`
- `libs/runtime/policy_bundle.py`

### Step 5.1 - Playbook Contract Inventory

No behavior change. Build a single enum/list of current playbooks and tactical names.

Known current concepts:

- breakout
- pullback
- reversal
- defensive
- vwap_reclaim_pullback and related tactical variants

### Step 5.2 - Policy Bundle Normalization

Introduce a typed normalization layer while preserving dict output.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_strategist_output_schema.py tests\test_strategy_policy_contract.py tests\test_scanner_strategy_frame_integration.py tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py -q
```

## Phase 6 - Script and Runtime Boundary Cleanup

### Goal

Align implementation with existing policy:

- scripts are process boundaries
- reusable logic lives in libs

Known current exceptions:

- `libs/agent/reporter.py` imports report generator scripts
- `libs/reporting/report_source_helpers.py` imports a check script
- `libs/read/kiwoom_broker_truth_common.py` imports `scripts.build_api_catalog`

### Steps

1. Move reusable script functions into `libs/reporting`, `libs/catalog`, or `libs/runtime`.
2. Keep scripts as thin wrappers.
3. Expand `tests/test_runtime_entrypoint_import_boundaries.py` to cover the new boundary.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_runtime_entrypoint_import_boundaries.py tests\test_reporter_script_wrappers.py tests\test_build_api_catalog.py -q
```

## Phase 7 - Documentation and Repository Hygiene

### Goals

- Fix mojibake in docs and config templates.
- Separate latest operational truth from historical daily patch notes.
- Stop tracking runtime-only outputs that should be ignored.

### Steps

1. Add docs/config UTF-8 scan test.
2. Repair or archive corrupted docs.
3. Create `docs/runtime/current_policy.md` as the latest operator-facing policy surface.
4. Keep `docs/daily_patch` as history only.
5. Audit tracked runtime artifacts such as `b.jsonl`, `_health.json`, and stale state backups.

Focused tests:

```text
venv\Scripts\python.exe -m pytest tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py -q
```

## Phase 8 - Broad Regression and Live Restart Policy

### When To Run Full Regression

Run broad tests after each workstream, not after every tiny extraction.

Suggested full command:

```text
venv\Scripts\python.exe -m pytest -q
```

### Live Restart Policy

Restart live session only after:

- tests for the touched workstream pass
- syntax check passes
- no unexpected diff appears in unrelated files
- the change is runtime-relevant

Command:

```text
scripts\restart_live_session.bat
```

### Rollback Policy

Rollback is by patch reversal, not by destructive git reset.

Rollback trigger examples:

- SELL intent emitted when previous behavior held
- hard stop blocked
- buy created without passing guard
- report authoritative PnL changes without explicit truth-source migration
- canonical artifact required field disappears
- live restart fails or stderr log is non-empty

## Suggested First Implementation Slice

Start with Phase 1.1:

- Extract VWAP breakdown confirmation from `graphs/nodes/monitor_node.py`.
- New module: `libs/runtime/monitor_exit_confirmation.py`.
- Keep function signature narrow.
- Keep output dict fields unchanged.
- Run only focused Monitor/Exit tests first.

This is the best first slice because it is recent, tested, and behaviorally small.

## Open Decisions

1. Whether to pause live trading before larger Executor refactors.
2. Whether to enforce docs/config UTF-8 in CI immediately or first run it as warning-only.
3. Whether to keep `docs/ko` corrupted files and repair gradually or archive and regenerate.
4. Whether to make `trade_truth_resolver` authoritative before or after Kiwoom split-fill aggregation is complete.

