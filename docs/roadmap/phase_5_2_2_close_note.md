# Phase 5-2-2 Close Note

## Summary
Phase `5-2-2: Visibility (news -> symbol linkage)` is now in a good stopping state.

Within the intended scope, we have made the strategist news context legible in
non-UI reporting surfaces without turning this step into a policy project or a
report-writing overhaul.

This note does not replace the roadmap.
It only records what is considered complete enough for the current `5-2-2`
slice.

## What Was Completed
The current implementation now covers these behaviors:
- a read-only linkage view can connect strategist news/query context to candidate hints and the selected symbol
- the same linkage view can compare the selected symbol with the runner-up symbol
- the linkage is visible in non-UI reporting surfaces
- the linkage is carried into trade-level story/bundle artifacts as additive data

In practice, this means the system can now show:
- which news query targets strategist used
- which symbols strategist hinted
- which candidate hypotheses were present
- whether the selected symbol stayed inside strategist candidate hints
- whether the runner-up also had similar linkage
- a compact selected-vs-runner-up comparison summary

## Scope Boundary
This step was intentionally kept below policy ownership and below report
refinement.

The completed work belongs to:
- read-model assembly
- reporting visibility
- additive artifact enrichment

The completed work does not attempt to do:
- strategist policy schema changes
- scanner execution logic changes
- monitor policy changes
- report narrative redesign
- UI product work

## Why 5-2-2 Can Pause Here
The practical goal of `5-2-2` was to make an existing flow easier to inspect:

`news -> strategist frame -> candidate comparison -> selected symbol`

That goal is now met in a reusable way:
- `libs/reporting/strategy_read_model.py` owns the linkage assembly
- `libs/reporting/agent_pipeline_trace.py` surfaces it in non-UI trace output
- `libs/reporting/trade_story_pipeline.py` carries it into trade story / lifecycle artifacts

Further work at this point would start shifting from "visibility" into
"report refinement" or "policy semantics", which belongs to later steps.

## What Should Not Be Added Here
Do not expand `5-2-2` into:
- stronger strategist/scanner coupling semantics
- policy reasoning ownership
- execution-time decision changes
- broad natural-language report rewriting

Those belong to later roadmap steps, especially:
- `5-2-3: Report Refinement`
- `5-3: Policy Structuring`

## Test Snapshot
Targeted regression coverage currently passes for the implemented slice:
- `tests/test_strategy_read_model.py`
- `tests/test_agent_pipeline_trace_report.py`
- `tests/test_trade_story_pipeline_enrichment.py`

## Next Step
The next roadmap step should be `5-2-3: Report Refinement`.

That is the right place to take the newly visible linkage data and decide how
it should appear in richer trade/daily/operator reporting outputs.

## Practical Read
Treat `5-2-2` as complete enough for now.

The system can already expose the strategist news-to-symbol linkage in a
non-UI, additive, reusable way. The next step is not more visibility plumbing;
it is deciding how those visible structures should be turned into better report
content.
