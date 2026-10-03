# M7.5 Operations Command Center

## Purpose

Provide one authenticated, read-only operating surface for answering four
questions without inspecting directories manually:

1. What completed, when, and from which source?
2. Which operational or evidence issues need attention?
3. How did a trade move through the agent decision chain?
4. What changed from the prior operating day or after the actual exit?

## Read Model

`GET /api/v1/operations` reuses existing evidence only:

- dated Preopen and Closeout manifests
- existing operational anomaly policy output
- current runtime status
- normalized trade bundles

It does not introduce a new evaluation score or infer missing agent decisions.

## UI Modules

| Module | Responsibility |
| --- | --- |
| `OperationsTimeline` | Preopen, entry, exit and Closeout chronology |
| `OperationsAlertPanel` | Existing anomaly and manifest issue consolidation |
| `DecisionLineagePanel` | Strategist through Execution artifact lineage |
| `OperationsComparisonPanel` | Prior-day configuration and post-exit observation diff |

## Safety

- GET only; POST is rejected by the router.
- `read_only=true` and `execution_callable=false` are explicit response fields.
- No Trading Runtime import or write mount is added.
- No order, restart, approval, threshold, prompt or evaluation mutation exists.
- Post-exit comparison is labeled as retrospective evidence, never an action.

## Validation

- Operations and runtime API tests passed.
- Web TypeScript production build passed.
- Web unit tests passed.
- The page is private-profile navigation and remains behind Cloudflare Access.
