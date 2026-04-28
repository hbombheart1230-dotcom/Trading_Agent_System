# Report Runtime Regression Plan (2026-04-16)

## Goal

Make trade report testing follow the same context as the real intraday runtime.

This plan exists because recent regressions passed helper-level tests but still failed in live bundle assembly. The gap was not in markdown rendering alone. The gap was in lifecycle replay, artifact propagation, and final bundle handoff.

## What Failed

- Helper-level tests passed while live bundle output still produced broken lifecycle artifacts.
- `entry.json`, `hold.json`, `lifecycle_bundle.json`, and `ai_trade_report_input.json` drifted apart.
- Partial recovered closed trades were not validated against real runtime expectations.
- Final live bundle handoff used sparse lifecycle data even after payload enrichment.

## Core Principle

Do not treat trade report quality as a single-file markdown problem.

The runtime contract is the full chain:

1. `entry.json`
2. `hold.json`
3. `exit.json`
4. `lifecycle_bundle.json`
5. `ai_trade_report_input.json`
6. `ai_trade_report.json`
7. `ai_trade_report.md`

Regression coverage is incomplete until the same fact is validated across this chain.

## Quality Axes

### 1. Lifecycle Completeness

Closed trades must expose:

- entry run id
- exit run id
- entry timestamp
- exit timestamp
- holding duration
- entry reason
- exit reason

Hard failure examples:

- closed trade with empty `entry.run_id`
- closed trade with `hold_duration=00:00:00` because entry timing was missing
- closed trade with empty `linked_run_ids`

### 2. Provenance Fidelity

Each section must report the real source honestly.

- canonical when canonical artifact exists
- direct artifact when trade artifact is the real source
- fallback only when reconstruction actually occurred
- missing when file does not exist

Hard failure examples:

- artifact path points to a file that does not exist
- provenance says canonical while source was reconstructed
- report says linked while same-day reporter file is absent

### 3. Cross-Artifact Consistency

Facts must remain stable across all downstream artifacts.

Examples:

- `entry.json.run_id` must match `lifecycle_bundle.lifecycle.entry.run_id`
- selected symbol/rank must match between `entry.json` and `ai_trade_report_input.json`
- hold duration must match between `hold.json`, `lifecycle_bundle.json`, and `ai_trade_report_input.json`

### 4. Report Diagnostic Value

The report must answer:

- why we entered
- why we held
- why we exited
- what failed: scanner, entry, hold, exit, or execution
- which memory phase is being described: strategist input, scanner application, monitor application, or latest commander state

This axis is not about fluent writing alone. It is about operational usefulness.

### 5. Runtime Parity

Tests must exercise the same code path the live runtime uses.

Priority order:

1. actual bundle replay
2. targeted repair replay
3. helper-level unit tests

Helper tests are necessary but no longer sufficient.

### 6. Repairability

If live artifacts degrade, targeted repair must restore them without schema drift.

Repair output must be checked against the same artifact chain as the original live path.

## Test Layers

### Layer A. Pure Helper Tests

Purpose:

- fast validation of deterministic transformations
- string normalization
- provenance helper behavior

Examples:

- `trade_report_ai`
- `trade_story_pipeline`
- provenance merge helpers

### Layer B. Lifecycle Assembly Tests

Purpose:

- validate `_build_trade_lifecycles`
- validate recovery metadata
- validate partial lifecycle marking

Required checks:

- sell-only lifecycle stays partial
- recovered entry without execution evidence is marked partial
- missing entry timing does not become fake zero-second hold

### Layer C. Runtime Replay Tests

Purpose:

- replay representative event/evidence fragments through `run_live_execution_bundle_report.py`
- assert actual written artifacts

Required checks:

- `entry.json`
- `hold.json`
- `exit.json`
- `lifecycle_bundle.json`
- `ai_trade_report_input.json`

### Layer D. Acceptance Tests

Purpose:

- validate one or more real trade directories after runtime replay or targeted repair
- validate final report artifacts

Required checks:

- `ai_trade_report.json`
- `ai_trade_report.md`
- provenance state
- reporter linkage state
- memory application phase lines

## Golden Acceptance Rules

For closed trades, fail the test if any of the following is true:

- empty `entry.run_id`
- empty `exit.run_id`
- empty `linked_run_ids`
- `selected_rank == 0`
- `candidate_count == 0` when scanner evidence exists
- `hold_duration == "00:00:00"` caused by missing entry timing
- all major section provenance values collapse to fallback
- `실제로 적용된 결정론적 메모리 bias` collapses strategist prompt policy, scanner application, monitor application, and latest commander policy into one ambiguous line
- scanner `not_applied` and monitor `applied` traces in the same trade are rendered as a contradiction instead of phase-separated runtime facts

## Runtime Execution Policy For Validation

When validating report quality during development:

1. run targeted bundle repair or replay first
2. regenerate the canonical report with the default deterministic no-LLM mode
3. use `local_debug` only when a non-destructive `.local_debug` comparison artifact is needed
4. run a real LLM acceptance pass with `--with-llm` only after deterministic output is acceptable

Credit minimization is the default batch/manual regeneration policy. Live closed-trade first-write still uses the report LLM, and runtime parity plus acceptance confidence still require small curated `--with-llm` checks after major report changes.

## Immediate Next Steps

1. Build and maintain a golden trade matrix
2. Add replay-driven regression tests for representative lifecycle patterns
3. Add acceptance assertions for the full artifact chain
4. Run real LLM acceptance checks on a small curated trade set after major report changes
