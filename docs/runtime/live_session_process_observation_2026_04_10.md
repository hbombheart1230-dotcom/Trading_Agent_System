# Live Session Process Observation 2026-04-10

## Summary
Current runtime launch is effectively **single entrypoint**, but not yet **single long-lived process**.

- Official operator entrypoint remains `scripts/run_session.py`
- Intraday live runtime currently appears as a parent/worker pair
- Additional report bundle subprocesses may appear when intraday trade artifact generation is triggered

This explains why operators can still see multiple Python or console windows even though runtime startup was consolidated to one command.

## What We Observed
During live operation on `2026-04-10`, the process tree looked like this:

1. Session parent
   - `scripts/run_session.py`
2. Session worker / lock owner
   - `scripts/run_session.py`
   - owns `data/state/m13_live_loop.lock`
3. Optional report subprocesses
   - `scripts/run_live_execution_bundle_report.py`
   - can appear after execution/report generation triggers

This means the current runtime model is:

- single startup command
- multi-process runtime ownership
- optional subprocess sidecars

## Why This Happens
There are two separate reasons:

1. The intraday session loop is not currently owned by only one long-lived Python process.
   - `scripts/run_session.py` delegates to the live loop backend
   - lock ownership is held by the worker-side runtime

2. Reporting still uses subprocess execution for intraday bundle generation.
   - `libs/reporting/intraday_trade_reports.py`
   - `scripts/run_live_execution_bundle_report.py`

Even after report dedupe improvements, the architecture still permits child processes.

## Operational Interpretation
This is not the same as “multiple competing trading sessions.”

What is expected:
- one official runtime entrypoint
- one lock owner
- one active live session chain

What is still imperfect:
- the live session can still look like two Python processes
- report subprocesses can still make the runtime look noisier than expected

## Current Safe Rule
When checking whether runtime is healthy, prefer these signals over raw window count:

1. `data/state/m13_live_loop.lock` exists and heartbeat updates
2. latest canonical run is still being produced
3. only one active lock owner exists
4. report subprocess count is zero or transiently small

## What This Document Is Not
This note does not change runtime behavior.

It records the current state so the next cleanup phase can target:
- single visible session behavior
- eventual single long-lived process ownership
