# M7.2 Windows Host Supervisor and Watchdog Visibility

Date: 2026-08-27

## Purpose

Keep Trading Main on the Windows host while making a stopped, hung, duplicated,
or ownership-inconsistent session recoverable without daily manual process
inspection. The Docker observability stack remains read-only and exposes the
supervisor result; it does not control Trading Main.

## Runtime Flow

```text
Windows Task Scheduler (every 5 minutes, regular session)
  -> scripts/start_trading_day.py --mode watchdog
  -> observe lock heartbeat and logical process tree
  -> apply bounded supervisor policy
  -> use the existing clean restart path only when recovery is allowed
  -> write current state and immutable per-run history

Read-only API/Web containers
  -> display current policy state and recent watchdog history
```

## Fixed Recovery Policy

| Condition | Detection | Action |
| --- | --- | --- |
| Main stopped | No live session | Clean restart |
| Main hung | Heartbeat older than 300 seconds | Clean restart |
| Main duplicated | More than one logical process tree | Clean restart |
| Ownership mismatch | Lock owner absent from process tree | Clean restart |
| Healthy | One session and current heartbeat | Observe only |

Safety limits:

* restart cooldown: 600 seconds;
* maximum automatic recoveries: 3 per trading day;
* no recovery based on trade count, candidate count, event volume, or PnL;
* the scheduled pre-open start is not counted as an automatic recovery;
* all recovery uses the existing clean restart implementation;
* when the limit or cooldown blocks recovery, the issue remains visible and is
  never reported as healthy.

## Artifacts

Current state:

```text
data/state/trading_day_supervisor.json
reports/runtime/trading_day_status/latest.json
```

Per-run history:

```text
reports/runtime/trading_day_status/history/YYYY-MM-DD/
  YYYYMMDDHHMMSS_watchdog.json
```

The history records the observed state before and after the watchdog action,
the reason, action, restart count, residual issue, and blockers. It is the
authoritative operator log for watchdog decisions.

## Operator Check

Open `http://127.0.0.1:3000/` and use the Overview page.

* `Trading Main` shows current heartbeat, logical session count, watchdog age,
  and market expectation.
* `Watchdog / 자동 복구` shows today's recovery count, latest action and reason,
  residual issues, and the ten most recent checks.
* A `정상 -> 정상` row with `정상 유지` means the watchdog ran and took no
  action.
* An `응답 없음 -> 정상` row with `복구 완료` means a stale Main was restarted.
* `복구 제한` means cooldown or the daily limit prevented another restart and
  requires operator review.

Host-level fallback checks:

```powershell
Get-ScheduledTaskInfo -TaskName TradingAgent-MockExamDay-SessionWatchdog
Get-Content reports/runtime/trading_day_status/latest.json
Get-Content data/state/trading_day_supervisor.json
docker compose -f deploy/compose/compose.yaml ps
```

## API Boundary

```text
GET /api/v1/runtime/status
GET /api/v1/runtime/watchdog-history?limit=10
```

Both routes declare `read_only=true` and `execution_callable=false`. There is
no HTTP start, stop, restart, kill, order, or Task Scheduler action.

## Operational Limits

Docker Compose restarts the API and Web containers after their process exits.
The Windows scheduled watchdog supervises Trading Main during its configured
regular-session window. This design does not wake a powered-off PC, bypass a
Windows logout requirement for interactive Kiwoom operation, or restart Main
outside the scheduled session window.

## Verification

```text
Runtime/API regression: 81 passed, 1 skipped
Strict TypeScript and production Docker build: passed
Trading Main restart during implementation: none
```
