# Code Structure Policy

## Purpose
Keep runtime code easier to audit, replace, and debug by narrowing ownership aggressively.

## Rules
- Scripts stay thin.
- Modules stay thin.
- File count may increase if ownership becomes clearer.
- Do not keep adding unrelated helpers into an existing module for convenience.

## Script Policy
- Scripts are boundary only.
- Scripts may do bootstrap, CLI parsing, one-shot orchestration, or manual inspection.
- Scripts must not become runtime truth owners.
- If logic is needed by runtime, tests, or more than one script, move it into `libs/*`.

## Module Policy
- One module should own one narrow responsibility.
- Prefer several short modules over one long mixed-responsibility module.
- If a module starts mixing:
  - API access
  - normalization
  - reconciliation
  - report shaping
  split it.
- Public facade modules are acceptable, but heavy logic should live in smaller leaf modules.

## Patch Policy
- Do the smallest patch that creates a cleaner ownership boundary.
- Do not hide I/O deep inside pure transformation code unless that module is explicitly the I/O owner.
- Prefer injection over hidden global lookups when wiring runtime truth into pure builders.

## Kiwoom-Specific Application
- Token/auth, API catalog, request building, and broker truth readers should stay modular.
- Reconciliation and demo scripts must remain wrappers over `libs/*` owners.
- Broker truth hot paths should depend on module owners, not scripts.

## Review Questions
- Is this script doing owner work?
- Is this module too long for its responsibility?
- Are unrelated responsibilities being added to an existing file?
- Would a new small file make the ownership boundary clearer?

## Current Direction
- Thin script
- Thin module
- Narrow ownership
- Add files freely if that keeps responsibilities short and explicit
