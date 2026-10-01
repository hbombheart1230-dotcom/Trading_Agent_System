# 2026-10-01 - Storage and Temporary-Artifact Hygiene Rule

## Scope

Established the canonical storage-hygiene rule in `docs/ground_rules/AGENT_RULES.md` for all human and agent work.
This is a governance change only; it changes no trading, Docker runtime, scheduler, UEF, or canonical evidence.

## Rule

- Temporary engineering resources follow create, use, verify-preservation, then cleanup.
- Agents reuse compatible worktrees where possible, create at most one temporary worktree when isolation is required,
  and remove completed worktrees after commits are preserved.
- Successful test runs leave no repo-local pytest scratch. Debug artifacts and temporary large copies have bounded
  retention and are removed after use.
- Docker cleanup is evidence-aware: inspect disk use, remove only proven-unused temporary resources, retain runtime,
  rollback, and frozen-acceptance artifacts, and never run broad destructive pruning without approval.
- Canonical market, broker, runtime, UEF, registry, report, and audit evidence is not cleanup material.

## Current cleanup verification

- The formerly registered `C:\Trading_Agent_System_p1_2_fix` worktree is absent.
- `C:\Trading_Agent_System_p1_2_final` is no longer a registered worktree; its empty residual directory contains no
  repository metadata or work product and is not treated as canonical evidence.
- Other pre-existing temporary worktrees and active/incident Docker evidence are preserved because their ownership or
  purpose is not established by this task.
