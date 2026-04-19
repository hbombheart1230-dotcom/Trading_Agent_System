# Script And Report Reduction Policy (2026-04-19)

## Goal

This policy fixes one operating rule for future development:

- do not attempt one-shot cleanup
- reduce scripts and reports continuously as the system is improved
- prune only when the role is clear and replacement ownership is already established

The point is not to delay cleanup.
The point is to stop creating new legacy surfaces while work continues.

## Core Principle

When a development path touches an unnecessary script, wrapper, or report surface, reduce it during that slice if the ownership contract is already clear.

Do not wait for a giant cleanup phase.
Do not do a blind mass-deletion phase either.

## Script Policy

### Allowed Role

Scripts should be thin boundaries only.

Allowed script responsibilities:

- CLI argument parsing
- process boundary
- lock / queue / restart / watchdog handling
- manual repair entrypoint
- batch kickoff

### Disallowed Role

Scripts should not own:

- business policy
- report assembly logic
- memory packet shaping
- strategy/scanner/monitor decision logic
- duplicate orchestration already shared by another runtime path

### Reduction Rule

If a script grows business logic while touching the current workstream:

1. move the logic into `libs/*` or `graphs/*`
2. leave the script as a wrapper only
3. do not add another wrapper layer above it

## Report Policy

### A report survives only if it clearly belongs to one of these roles

1. `runtime_source`
- source-of-truth runtime artifact

2. `operator_surface`
- something operators directly read

3. `memory_source`
- source material for strategist / scanner / position refresh memory

4. `debug_only`
- required for replay, diagnostics, audit, or repair

If a report does not fit one of those roles, it should not remain a default generated artifact.

### Reduction Rule

When current work touches a low-value report:

1. classify it
2. confirm no critical consumer depends on it
3. disable default generation or retire it in the same slice if safe

Do not preserve a report just because it already exists.

## Development Sequence

For ongoing cleanup, use this sequence:

1. define the owner and consumer
2. confirm whether an existing module/report/read-model already serves the purpose
3. implement the current feature
4. prune overlapping script/report surfaces touched by that feature
5. update the contract doc

This means cleanup happens continuously, but never blindly.

## Existing-First Rule

Before adding a new module, report, or runtime-memory artifact:

1. search for an existing owner or overlapping surface
2. prefer upgrading, adapting, or shrinking the existing surface
3. add something new only when the existing contract is clearly insufficient

This repo should prefer:

- owner promotion over wrapper multiplication
- adapter reduction over parallel read models
- report reinterpretation over report duplication
- additive extension only when reuse is not coherent

## Practical Rule For This Repo

### Good examples

- while stabilizing live trade-report runtime, reduce `scripts/run_live_execution_bundle_report.py`
- while designing strategist memory, redefine `reports/symbols` instead of preserving it as a vague operator surface
- while strengthening market memory, reinterpret `reporter_analysis` as compressed upstream input instead of generic prose output

### Bad examples

- deleting all rarely used reports before memory contracts are defined
- adding a new report because an old one feels messy
- keeping a report “just in case” without a named consumer
- moving business logic into a new script because it is faster in the moment

## Current Intent

For the current workstream:

- trade-report runtime stays on continuous script reduction
- report cleanup follows the runtime memory contracts
- `decision_story` and `run_cards` remain prune-first examples
- `symbols` is not a delete-first surface; it is a redefine-first surface

## Decision Standard

The standard is:

- not “clean everything now”
- not “keep everything until later”
- but “if this slice proves something is unnecessary, cut it now”

That is the operating policy going forward.
