# 2026-08-27 Scheduled Intelligence and Host Supervisor

## Changes

* Added bounded Windows Main automatic recovery and watchdog history.
* Added Preopen/Closeout scheduled job manifests without new scheduler tasks.
* Added a preopen briefing assembled from the existing macro and Strategist artifacts.
* Added a memory delivery receipt with active versus advisory semantics.
* Added a daily intelligence index assembled from existing Closeout artifacts.
* Added read-only Overview panels for Watchdog recovery and scheduled intelligence.

## Trading Behavior

No Scanner, Strategist, Monitor, Commander, entry, exit, ranking, order, or
risk policy was changed. No additional LLM call was introduced.

## Live Result

The 08:50 Preopen completed successfully. Main was cleanly restarted at 13:12
with no open positions or pending orders, then returned with one logical
session, a fresh heartbeat and empty stderr.

Final regression completed with `2646 passed, 1 skipped` for Python and
`14 passed` for the Web unit suite. The live process tree remained normal
with one logical session throughout verification.
