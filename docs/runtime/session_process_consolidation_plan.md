# Session Process Consolidation Plan

## Goal
Move from:

- single entrypoint
- multi-process runtime

to:

- single entrypoint
- single visible session
- eventually single long-lived runtime process

without changing trading semantics.

## Current Baseline
Current runtime already has:

- official entrypoint: `scripts/run_session.py`
- lock-based single active session guard
- report subprocess dedupe improvements

What remains:

- parent/worker split is still visible
- report jobs still use subprocess execution

## Target End State
The operator should be able to think of the runtime as:

- one session
- one main Python process
- optional internal tasks that do not create extra visible console noise

## Recommended Rollout

### Step 1: Single Visible Session
Keep internal child ownership if necessary, but make the runtime operationally appear as one session.

Candidate work:
- reduce visible console spawning for report sidecars
- keep report jobs detached and silent
- keep a single authoritative lock owner
- ensure all subprocesses are clearly tagged as helper tasks, not session owners

This is the lowest-risk improvement path.

### Step 2: Single Runtime Owner
Collapse the parent/worker split so the live loop is owned directly by one long-lived Python process.

Candidate work:
- make `scripts/run_session.py` own the intraday loop directly
- remove redundant delegation where safe
- keep lock acquisition / refresh / release in the same process that owns the session loop

This is cleaner, but more invasive.

### Step 3: Background Work as Internal Tasks
Where feasible, convert helper work from subprocess spawning into:

- synchronous bounded calls
- internal task queue
- or explicit off-hours reporting jobs

This should be done only after session ownership is stable.

## Non-Goals
This consolidation plan does not propose:

- strategy changes
- scanner logic changes
- execution semantics changes
- guard precedence changes

The cleanup is operational, not behavioral.

## Immediate Practical Guidance
Until the consolidation work is done, operators should treat:

- `scripts/run_session.py` parent + worker
as one session chain,

and treat:

- `scripts/run_live_execution_bundle_report.py`
as helper subprocesses, not independent runtimes.

## Success Criteria
The cleanup can be considered complete when:

1. one official runtime command starts one visible session chain
2. one lock owner is clearly identifiable
3. report helpers do not create lingering visible console clutter
4. operators no longer confuse helper subprocesses with extra live sessions
