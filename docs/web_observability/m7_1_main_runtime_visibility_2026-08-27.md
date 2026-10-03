# M7.1 Main Runtime Visibility

Date: 2026-08-27

## Purpose

Expose the Windows Trading Main state in the read-only observability UI without
moving Trading Main into Docker and without adding another daemon, container,
or control path.

This surface answers four operator questions:

1. Is Trading Main expected to be running now?
2. Is its heartbeat current?
3. Are the parent and child Python processes one logical session?
4. Is there evidence of more than one independent Main session?

## Minimal Architecture

```text
Windows Trading Main
  -> data/state/m13_live_loop.lock (heartbeat, about 60 seconds)

Existing Windows Watchdog
  -> reports/runtime/trading_day_status/latest.json (about 5 minutes)
  -> process tree normalization

Kiwoom market status
  -> data/state/kiwoom_market_status.json

Read-only API container
  -> GET /api/v1/runtime/status

Read-only Web container
  -> top-bar MAIN badge
  -> Overview Trading Main panel
```

No new scheduled task was created. The existing
`TradingAgent-MockExamDay-SessionWatchdog` task remains authoritative for the
5-minute Windows process observation.

## Logical Session Rule

Windows can show a launcher Python process and a child Python process for one
Trading Main run. Raw process count is therefore not session count.

* One independent root with parent/child descendants is one logical session.
* Two or more independent roots are duplicate logical sessions.
* A lock owner absent from the observed process tree is inconsistent.
* No lock outside the expected session is an expected stop.
* No lock during the expected regular session is an unexpected stop.

## State Contract

| State | Meaning |
| --- | --- |
| `RUNNING` | Lock heartbeat is at most 180 seconds old. |
| `DELAYED` | Heartbeat is 181-600 seconds old. |
| `STALE` | Heartbeat is over 600 seconds old. |
| `DUPLICATE` | Fresh watchdog evidence contains multiple logical roots. |
| `INCONSISTENT` | Lock, heartbeat, and observed process ownership disagree. |
| `STOPPED_EXPECTED` | Main is absent outside the expected regular session. |
| `STOPPED_UNEXPECTED` | Main is absent while regular-session execution is expected. |

Kiwoom market status is preferred for session expectation. The weekday clock
is only a fallback when there is no same-day Kiwoom status.

## Safety Boundary

* API route is GET-only.
* Response declares `read_only=true` and `execution_callable=false`.
* API reads bounded artifacts from existing read-only container mounts.
* Public profile hides PID/process details.
* The UI has no start, stop, restart, kill, or order controls.
* Trading Main remains a Windows host process.

## UI Surface

The global top bar shows the current MAIN state on every page. The Overview
page additionally shows heartbeat age, logical session count, normalized
process-tree state, watchdog freshness, and market state. It refreshes every
15 seconds without changing source collection frequency.

## Verification

```text
Python runtime/API tests: 16 passed
Web presentation tests: 3 passed
Strict TypeScript and production Docker build: passed
API/Web Compose containers: healthy
GET /api/v1/runtime/status: 200
Observed pre-market state: STOPPED_EXPECTED / AVAILABLE
Existing watchdog task: last result 0, missed runs 0, next run 09:05
```

The next regular-session watchdog observation will populate the additive
process-tree fields. Legacy watchdog files remain readable and are reported as
`LEGACY_UNKNOWN` until refreshed.
